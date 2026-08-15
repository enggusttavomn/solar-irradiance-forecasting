r"""TimesNet compacto para previsao horaria multistep de GHI.

O nucleo do TimesNet transforma variacoes temporais 1D em variacoes 2D:
as frequencias dominantes de cada lote sao obtidas por FFT, cada periodo
selecionado define uma grade ``(ciclos, periodo)`` e convolucoes Inception 2D
extraem variacoes intra e interperiodos. As representacoes resultantes sao
ponderadas, por amostra, pelas amplitudes espectrais e recebem uma conexao
residual.

Esta implementacao e deliberadamente pequena e voltada ao problema global
univariado do artigo:

* entrada: historico de GHI com forma ``(lote, seq_len)`` ou
  ``(lote, seq_len, 1)``;
* saida: todos os horizontes em uma unica passagem, com forma
  ``(lote, pred_len)``;
* configuracao padrao: 336 horas de contexto e 72 horas de previsao;
* localidade: um embedding estatico opcional, compartilhado por todos os
  instantes da respectiva amostra.

O modulo produz previsoes na escala original, mas nao aplica restricoes
fisicas. O truncamento em zero e a mascara noturna devem ocorrer somente
depois da inversao de qualquer transformacao externa dos dados.
"""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn


def _inteiro_positivo(valor: object, nome: str) -> int:
    """Valida e devolve um hiperparametro inteiro estritamente positivo."""

    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    return valor


def fft_top_k_periods(x: Tensor, top_k: int) -> tuple[Tensor, Tensor]:
    """Seleciona os periodos dominantes nao nulos de um lote temporal.

    Args:
        x: Representacao temporal ``(lote, tempo, canais)``.
        top_k: Quantidade de frequencias dominantes. A frequencia zero (DC)
            nunca participa da selecao.

    Returns:
        Um par ``(periodos, amplitudes)``. ``periodos`` tem forma ``(top_k,)``
        e tipo inteiro; ``amplitudes`` tem forma ``(lote, top_k)`` e conserva
        o gradiente usado na agregacao adaptativa das representacoes.

    Notes:
        Como no TimesNet original, o periodo discreto associado ao indice
        espectral :math:`f` e calculado por ``tempo // f``.
    """

    if not isinstance(x, Tensor):
        raise TypeError("x deve ser um torch.Tensor.")
    if x.ndim != 3:
        raise ValueError("x deve ter forma (lote, tempo, canais).")
    if x.shape[0] < 1 or x.shape[2] < 1:
        raise ValueError("x nao pode conter lote ou canais vazios.")
    if x.shape[1] < 2:
        raise ValueError("A FFT requer pelo menos dois instantes.")
    if not x.is_floating_point():
        raise TypeError("x deve possuir tipo de ponto flutuante.")
    top_k = _inteiro_positivo(top_k, "top_k")

    # rfft possui floor(tempo / 2) bins estritamente positivos. Trabalhar
    # diretamente com o recorte [1:] torna impossivel selecionar o componente
    # DC, mesmo quando a serie tem uma media muito maior que sua oscilacao.
    espectro = torch.fft.rfft(x, dim=1)
    amplitudes = espectro.abs()
    n_frequencias_positivas = amplitudes.shape[1] - 1
    if top_k > n_frequencias_positivas:
        raise ValueError(
            "top_k excede a quantidade de frequencias nao nulas disponiveis."
        )

    amplitude_global = amplitudes.mean(dim=(0, 2))
    indices = torch.topk(amplitude_global[1:], k=top_k).indices + 1
    periodos = torch.div(x.shape[1], indices, rounding_mode="floor")
    amplitudes_por_amostra = amplitudes.mean(dim=2).index_select(1, indices)
    return periodos, amplitudes_por_amostra


# Nome em portugues para uso nos demais modulos do projeto.
selecionar_periodos_fft = fft_top_k_periods


class InceptionBlock2D(nn.Module):
    """Banco Inception de convolucoes 2D com nucleos impares multiescala."""

    def __init__(
        self,
        canais_entrada: int,
        canais_saida: int,
        *,
        num_kernels: int = 3,
    ) -> None:
        super().__init__()
        canais_entrada = _inteiro_positivo(canais_entrada, "canais_entrada")
        canais_saida = _inteiro_positivo(canais_saida, "canais_saida")
        num_kernels = _inteiro_positivo(num_kernels, "num_kernels")

        self.tamanhos_kernel = tuple(2 * indice + 1 for indice in range(num_kernels))
        self.convolucoes = nn.ModuleList(
            nn.Conv2d(
                in_channels=canais_entrada,
                out_channels=canais_saida,
                kernel_size=tamanho,
                padding=tamanho // 2,
            )
            for tamanho in self.tamanhos_kernel
        )
        for convolucao in self.convolucoes:
            nn.init.kaiming_normal_(
                convolucao.weight,
                mode="fan_out",
                nonlinearity="relu",
            )
            if convolucao.bias is not None:
                nn.init.zeros_(convolucao.bias)

    def forward(self, x: Tensor) -> Tensor:
        """Aplica todos os nucleos e calcula sua media, preservando a grade."""

        if x.ndim != 4:
            raise ValueError("x deve ter forma (lote, canais, ciclos, periodo).")
        resultados = torch.stack(
            [convolucao(x) for convolucao in self.convolucoes],
            dim=-1,
        )
        return resultados.mean(dim=-1)


# Alias descritivo em portugues, sem duplicar a implementacao.
BlocoInception2D = InceptionBlock2D


class TimesBlock(nn.Module):
    """Bloco periodico do TimesNet com agregacao espectral e residual."""

    def __init__(
        self,
        comprimento: int,
        d_model: int,
        d_ff: int,
        *,
        top_k: int = 3,
        num_kernels: int = 3,
    ) -> None:
        super().__init__()
        self.comprimento = _inteiro_positivo(comprimento, "comprimento")
        if self.comprimento < 2:
            raise ValueError("comprimento deve ser pelo menos 2.")
        self.d_model = _inteiro_positivo(d_model, "d_model")
        d_ff = _inteiro_positivo(d_ff, "d_ff")
        self.top_k = _inteiro_positivo(top_k, "top_k")
        if self.top_k > self.comprimento // 2:
            raise ValueError(
                "top_k excede as frequencias nao nulas do comprimento informado."
            )

        self.convolucao = nn.Sequential(
            InceptionBlock2D(
                self.d_model,
                d_ff,
                num_kernels=num_kernels,
            ),
            nn.GELU(),
            InceptionBlock2D(
                d_ff,
                self.d_model,
                num_kernels=num_kernels,
            ),
        )

    def _representacao_bidimensional(self, x: Tensor, periodo: int) -> Tensor:
        """Reorganiza tempo em ``(ciclos, periodo)`` e volta para 1D."""

        lote, comprimento, canais = x.shape
        comprimento_ajustado = math.ceil(comprimento / periodo) * periodo
        if comprimento_ajustado > comprimento:
            preenchimento = x.new_zeros(
                lote,
                comprimento_ajustado - comprimento,
                canais,
            )
            serie = torch.cat((x, preenchimento), dim=1)
        else:
            serie = x

        # [B, T, C] -> [B, C, ciclos, periodo], a imagem temporal do TimesNet.
        grade = (
            serie.reshape(lote, comprimento_ajustado // periodo, periodo, canais)
            .permute(0, 3, 1, 2)
            .contiguous()
        )
        grade = self.convolucao(grade)
        serie = (
            grade.permute(0, 2, 3, 1)
            .contiguous()
            .reshape(lote, comprimento_ajustado, canais)
        )
        return serie[:, :comprimento, :]

    def forward(self, x: Tensor) -> Tensor:
        """Extrai e agrega as ``top_k`` representacoes periodicas de ``x``."""

        if not isinstance(x, Tensor):
            raise TypeError("x deve ser um torch.Tensor.")
        if x.ndim != 3:
            raise ValueError("x deve ter forma (lote, tempo, d_model).")
        if x.shape[0] < 1:
            raise ValueError("O lote nao pode ser vazio.")
        if x.shape[1] != self.comprimento or x.shape[2] != self.d_model:
            raise ValueError(
                "A forma temporal de x difere de (comprimento, d_model)."
            )

        periodos, amplitudes = fft_top_k_periods(x, self.top_k)
        representacoes = [
            self._representacao_bidimensional(x, int(periodo.item()))
            for periodo in periodos
        ]
        empilhadas = torch.stack(representacoes, dim=-1)

        # Cada amostra pondera os mesmos periodos globais com suas proprias
        # amplitudes. Softmax evita escalas arbitrarias e soma exatamente um.
        pesos = torch.softmax(amplitudes, dim=1)[:, None, None, :]
        agregado = torch.sum(empilhadas * pesos, dim=-1)
        return x + agregado


def _codificacao_posicional(comprimento: int, d_model: int) -> Tensor:
    """Cria a codificacao senoidal fixa usada pelo embedding temporal."""

    posicao = torch.arange(comprimento, dtype=torch.float32).unsqueeze(1)
    divisores = torch.exp(
        torch.arange(0, d_model, 2, dtype=torch.float32)
        * (-math.log(10_000.0) / d_model)
    )
    codificacao = torch.zeros(comprimento, d_model, dtype=torch.float32)
    codificacao[:, 0::2] = torch.sin(posicao * divisores)
    if d_model > 1:
        codificacao[:, 1::2] = torch.cos(
            posicao * divisores[: codificacao[:, 1::2].shape[1]]
        )
    return codificacao.unsqueeze(0)


class TimesNetHorario(nn.Module):
    """TimesNet univariado global para previsao direta de varios horizontes.

    Args:
        seq_len: Quantidade de horas passadas. O padrao equivale a 14 dias.
        pred_len: Quantidade de horas futuras produzidas conjuntamente.
        d_model: Dimensao do embedding temporal.
        d_ff: Largura interna das convolucoes Inception.
        num_blocos: Quantidade de :class:`TimesBlock` empilhados.
        top_k: Frequencias dominantes processadas por bloco.
        num_kernels: Escalas convolucionais em cada banco Inception.
        num_localidades: Numero de localidades globais. Quando omitido, o
            ramo de embedding estatico nao e criado.
        dropout: Dropout aplicado ao embedding de entrada.
        epsilon: Estabilizador da normalizacao por janela.
    """

    def __init__(
        self,
        *,
        seq_len: int = 336,
        pred_len: int = 72,
        d_model: int = 16,
        d_ff: int = 32,
        num_blocos: int = 2,
        top_k: int = 3,
        num_kernels: int = 3,
        num_localidades: int | None = None,
        dropout: float = 0.1,
        epsilon: float = 1e-5,
    ) -> None:
        super().__init__()
        self.seq_len = _inteiro_positivo(seq_len, "seq_len")
        if self.seq_len < 2:
            raise ValueError("seq_len deve ser pelo menos 2.")
        self.pred_len = _inteiro_positivo(pred_len, "pred_len")
        d_model = _inteiro_positivo(d_model, "d_model")
        d_ff = _inteiro_positivo(d_ff, "d_ff")
        num_blocos = _inteiro_positivo(num_blocos, "num_blocos")
        top_k = _inteiro_positivo(top_k, "top_k")
        num_kernels = _inteiro_positivo(num_kernels, "num_kernels")
        if top_k > self.seq_len // 2:
            raise ValueError("top_k excede as frequencias nao nulas de seq_len.")
        if (
            isinstance(dropout, bool)
            or not isinstance(dropout, (int, float))
            or not math.isfinite(dropout)
            or not 0.0 <= dropout < 1.0
        ):
            raise ValueError("dropout deve pertencer ao intervalo [0, 1).")
        if (
            isinstance(epsilon, bool)
            or not isinstance(epsilon, (int, float))
            or not math.isfinite(epsilon)
            or epsilon <= 0.0
        ):
            raise ValueError("epsilon deve ser positivo e finito.")
        if num_localidades is not None:
            num_localidades = _inteiro_positivo(
                num_localidades,
                "num_localidades",
            )

        self.d_model = d_model
        self.num_localidades = num_localidades
        self.epsilon = float(epsilon)

        # Token embedding local: a convolucao circular conserva continuidade
        # nas extremidades da janela e segue o embedding da familia TimesNet.
        self.embedding_valor = nn.Conv1d(
            in_channels=1,
            out_channels=d_model,
            kernel_size=3,
            padding=1,
            padding_mode="circular",
        )
        self.register_buffer(
            "codificacao_posicional",
            _codificacao_posicional(self.seq_len, d_model),
            persistent=False,
        )
        self.embedding_localidade = (
            nn.Embedding(num_localidades, d_model)
            if num_localidades is not None
            else None
        )
        self.dropout = nn.Dropout(float(dropout))
        self.blocos = nn.ModuleList(
            TimesBlock(
                self.seq_len,
                d_model,
                d_ff,
                top_k=top_k,
                num_kernels=num_kernels,
            )
            for _ in range(num_blocos)
        )
        self.normalizacoes = nn.ModuleList(
            nn.LayerNorm(d_model) for _ in range(num_blocos)
        )

        # Cabeca multistep direta: todas as 72 horas sao previstas a partir
        # das 336 representacoes do contexto em uma unica passagem.
        self.projecao_temporal = nn.Linear(self.seq_len, self.pred_len)
        self.projecao_saida = nn.Linear(d_model, 1)

    def _validar_entrada(self, x: Tensor) -> Tensor:
        if not isinstance(x, Tensor):
            raise TypeError("x deve ser um torch.Tensor.")
        if x.ndim == 2:
            x = x.unsqueeze(-1)
        elif x.ndim != 3:
            raise ValueError(
                "x deve ter forma (lote, seq_len) ou (lote, seq_len, 1)."
            )
        if x.shape[0] < 1:
            raise ValueError("O lote nao pode ser vazio.")
        if x.shape[1] != self.seq_len or x.shape[2] != 1:
            raise ValueError(
                "x deve ter forma (lote, seq_len) ou (lote, seq_len, 1)."
            )
        if not x.is_floating_point():
            raise TypeError("x deve possuir tipo de ponto flutuante.")
        if not bool(torch.isfinite(x).all()):
            raise ValueError("x contem valores nao finitos.")
        return x

    def _embedding_de_localidade(
        self,
        ids_localidade: Tensor | None,
        lote: int,
        dispositivo: torch.device,
    ) -> Tensor | None:
        if self.embedding_localidade is None:
            if ids_localidade is not None:
                raise ValueError(
                    "ids_localidade foi informado, mas num_localidades nao foi."
                )
            return None
        if ids_localidade is None:
            raise ValueError(
                "ids_localidade e obrigatorio quando num_localidades e usado."
            )
        if not isinstance(ids_localidade, Tensor):
            raise TypeError("ids_localidade deve ser um torch.Tensor.")
        if ids_localidade.ndim != 1 or ids_localidade.shape[0] != lote:
            raise ValueError("ids_localidade deve ter forma (lote,).")
        if ids_localidade.dtype == torch.bool or ids_localidade.is_floating_point():
            raise TypeError("ids_localidade deve conter indices inteiros.")

        ids = ids_localidade.to(device=dispositivo, dtype=torch.long)
        if bool((ids < 0).any()) or bool((ids >= self.num_localidades).any()):
            raise ValueError("ids_localidade contem indice fora do intervalo.")
        return self.embedding_localidade(ids)

    def forward(
        self,
        x: Tensor,
        ids_localidade: Tensor | None = None,
    ) -> Tensor:
        """Preve todo o horizonte e devolve um tensor ``(lote, pred_len)``."""

        x = self._validar_entrada(x)
        media = x.mean(dim=1, keepdim=True).detach()
        desvio = torch.sqrt(
            x.var(dim=1, keepdim=True, unbiased=False) + self.epsilon
        ).detach()
        normalizado = (x - media) / desvio

        representacao = self.embedding_valor(
            normalizado.transpose(1, 2)
        ).transpose(1, 2)
        representacao = representacao + self.codificacao_posicional.to(
            dtype=representacao.dtype
        )
        localidade = self._embedding_de_localidade(
            ids_localidade,
            lote=x.shape[0],
            dispositivo=x.device,
        )
        if localidade is not None:
            representacao = representacao + localidade.unsqueeze(1)
        representacao = self.dropout(representacao)

        for bloco, normalizacao in zip(
            self.blocos,
            self.normalizacoes,
            strict=True,
        ):
            representacao = normalizacao(bloco(representacao))

        futuro = self.projecao_temporal(
            representacao.transpose(1, 2)
        ).transpose(1, 2)
        previsao_normalizada = self.projecao_saida(futuro).squeeze(-1)

        media = media[:, 0, 0].unsqueeze(1)
        desvio = desvio[:, 0, 0].unsqueeze(1)
        return previsao_normalizada * desvio + media


__all__ = [
    "BlocoInception2D",
    "InceptionBlock2D",
    "TimesBlock",
    "TimesNetHorario",
    "fft_top_k_periods",
    "selecionar_periodos_fft",
]
