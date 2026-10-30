"""DilatedRNN global para previsao direta de multiplos passos.

O modulo complementa a implementacao mensal escalar sem altera-la. Cada
camada aplica a recorrencia dilatada

    h[t] = tanh(W_x x[t] + W_h h[t-d] + b)

separando a sequencia em ``d`` classes de residuos. Cada classe e processada
por uma mesma ``torch.nn.RNN`` e depois recolocada na ordem cronologica. Essa
forma e matematicamente equivalente a manter uma fila de ``d`` estados, mas
evita um laco Python por instante durante o treinamento de series horarias.
"""

from __future__ import annotations

from collections.abc import Sequence
import math

import torch
from torch import Tensor, nn


def _inteiro_positivo(valor: object, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    return valor


class CamadaRNNDilatada(nn.Module):
    """Camada recorrente em que cada estado consulta ``dilatacao`` passos atras."""

    def __init__(
        self,
        tamanho_entrada: int,
        tamanho_oculto: int,
        *,
        dilatacao: int,
    ) -> None:
        super().__init__()
        self.tamanho_entrada = _inteiro_positivo(
            tamanho_entrada, "tamanho_entrada"
        )
        self.tamanho_oculto = _inteiro_positivo(tamanho_oculto, "tamanho_oculto")
        self.dilatacao = _inteiro_positivo(dilatacao, "dilatacao")
        self.rnn = nn.RNN(
            input_size=self.tamanho_entrada,
            hidden_size=self.tamanho_oculto,
            num_layers=1,
            nonlinearity="tanh",
            batch_first=True,
        )

    def forward(self, x: Tensor) -> Tensor:
        if not isinstance(x, Tensor):
            raise TypeError("x deve ser um torch.Tensor.")
        if x.ndim != 3:
            raise ValueError("x deve ter forma (lote, tempo, variaveis).")
        if x.shape[0] < 1 or x.shape[1] < 1:
            raise ValueError("x nao pode conter lote ou sequencia vazios.")
        if x.shape[2] != self.tamanho_entrada:
            raise ValueError("A quantidade de variaveis de x e incompatível.")
        if not x.is_floating_point():
            raise TypeError("x deve possuir tipo de ponto flutuante.")

        # Para uma dilatacao d, os indices r, r+d, r+2d, ... formam uma RNN
        # convencional. Todas as classes usam os mesmos pesos, como exige a
        # recorrencia dilatada original.
        saidas_por_residuo: list[Tensor] = []
        for residuo in range(min(self.dilatacao, x.shape[1])):
            subsequencia = x[:, residuo :: self.dilatacao, :]
            saida, _ = self.rnn(subsequencia)
            saidas_por_residuo.append(saida)

        cronologica = [
            saidas_por_residuo[indice % self.dilatacao][
                :, indice // self.dilatacao, :
            ]
            for indice in range(x.shape[1])
        ]
        return torch.stack(cronologica, dim=1)


class DilatedRNNDireta(nn.Module):
    """Codificador DilatedRNN global com cabeca multistep direta.

    Args:
        seq_len: numero de instantes passados por amostra.
        pred_len: numero de instantes futuros previstos conjuntamente.
        dilatacoes: salto recorrente de cada camada.
        unidades: largura comum ou uma largura por camada.
        unidades_densas: largura da representacao anterior a saida.
        num_localidades: quantidade de series do modelo global.
        dimensao_embedding_localidade: largura do identificador aprendido.
        dropout: dropout aplicado antes da cabeca de previsao.
    """

    def __init__(
        self,
        *,
        seq_len: int,
        pred_len: int,
        dilatacoes: Sequence[int] = (1, 2, 4),
        unidades: int | Sequence[int] = 16,
        unidades_densas: int = 16,
        num_localidades: int,
        dimensao_embedding_localidade: int = 8,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        self.seq_len = _inteiro_positivo(seq_len, "seq_len")
        self.pred_len = _inteiro_positivo(pred_len, "pred_len")
        self.num_localidades = _inteiro_positivo(
            num_localidades, "num_localidades"
        )
        unidades_densas = _inteiro_positivo(unidades_densas, "unidades_densas")
        dimensao_embedding_localidade = _inteiro_positivo(
            dimensao_embedding_localidade,
            "dimensao_embedding_localidade",
        )
        if (
            isinstance(dropout, bool)
            or not isinstance(dropout, (int, float))
            or not math.isfinite(dropout)
            or not 0.0 <= float(dropout) < 1.0
        ):
            raise ValueError("dropout deve pertencer a [0, 1).")

        dilatacoes = tuple(dilatacoes)
        if not dilatacoes:
            raise ValueError("dilatacoes nao pode ser vazia.")
        for dilatacao in dilatacoes:
            _inteiro_positivo(dilatacao, "dilatacao")
        if any(dilatacao > self.seq_len for dilatacao in dilatacoes):
            raise ValueError("Nenhuma dilatacao pode exceder seq_len.")

        if isinstance(unidades, int):
            larguras = (unidades,) * len(dilatacoes)
        else:
            larguras = tuple(unidades)
            if len(larguras) != len(dilatacoes):
                raise ValueError("unidades deve ter um valor por dilatacao.")
        for largura in larguras:
            _inteiro_positivo(largura, "unidades")

        camadas: list[nn.Module] = []
        tamanho_entrada = 1
        for dilatacao, largura in zip(dilatacoes, larguras, strict=True):
            camadas.append(
                CamadaRNNDilatada(
                    tamanho_entrada,
                    largura,
                    dilatacao=dilatacao,
                )
            )
            tamanho_entrada = largura
        self.camadas = nn.ModuleList(camadas)
        self.dilatacoes = dilatacoes
        self.larguras = larguras
        self.embedding_localidade = nn.Embedding(
            self.num_localidades,
            dimensao_embedding_localidade,
        )
        self.cabeca = nn.Sequential(
            nn.Linear(
                larguras[-1] + dimensao_embedding_localidade,
                unidades_densas,
            ),
            nn.ReLU(),
            nn.Dropout(float(dropout)),
            nn.Linear(unidades_densas, self.pred_len),
        )

    def forward(self, x: Tensor, ids_localidade: Tensor) -> Tensor:
        if not isinstance(x, Tensor) or not isinstance(ids_localidade, Tensor):
            raise TypeError("x e ids_localidade devem ser torch.Tensor.")
        if x.ndim == 2:
            x = x.unsqueeze(-1)
        if x.ndim != 3 or x.shape[1:] != (self.seq_len, 1):
            raise ValueError("x deve ter forma (lote, seq_len) ou (lote, seq_len, 1).")
        if not x.is_floating_point():
            raise TypeError("x deve possuir tipo de ponto flutuante.")
        if ids_localidade.ndim != 1 or len(ids_localidade) != len(x):
            raise ValueError("ids_localidade deve ter forma (lote,).")

        ids = ids_localidade.to(device=x.device, dtype=torch.long)
        if bool((ids < 0).any()) or bool((ids >= self.num_localidades).any()):
            raise ValueError("ids_localidade contem indice fora do intervalo.")

        representacao = x
        for camada in self.camadas:
            representacao = camada(representacao)
        estado_final = representacao[:, -1, :]
        combinado = torch.cat(
            (estado_final, self.embedding_localidade(ids)),
            dim=1,
        )
        return self.cabeca(combinado)


__all__ = ["CamadaRNNDilatada", "DilatedRNNDireta"]

