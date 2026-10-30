"""Baselines GHI-only: GRU, Transformer completo e Informer compacto.

Implementacao PyTorch das formulacoes, sem covariaveis meteorologicas/calendario.
Informer segue Zhou et al. (AAAI 2021, doi:10.1609/aaai.v35i12.17325):
ProbSparse no encoder/decoder, distilacao convolucional e saida generativa.
Referencia de verificacao: https://github.com/zhouhaoyi/Informer2020
Adaptacoes declaradas: dimensoes compactas, projecao linear do GHI, identidade
estatica, sem embeddings de calendario, mix=False, amostragem deterministica
na avaliacao. Nao se trata de reproducao dos hiperparametros do artigo original.
"""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class GRUDireta(nn.Module):
    """Mesmo encoder/cabeca da LSTM canonica, substituindo somente a celula."""

    def __init__(self, seq_len: int, pred_len: int, num_localidades: int):
        super().__init__()
        self.seq_len, self.pred_len = seq_len, pred_len
        self.encoder = nn.GRU(1, 32, num_layers=1, batch_first=True)
        self.embedding_localidade = nn.Embedding(num_localidades, 8)
        self.cabeca = nn.Linear(32 + 8, pred_len)

    def forward(self, x: Tensor, ids: Tensor) -> Tensor:
        if x.ndim == 2:
            x = x.unsqueeze(-1)
        if x.shape[1:] != (self.seq_len, 1):
            raise ValueError("Contexto GRU incompatível.")
        _, estado = self.encoder(x)
        return self.cabeca(torch.cat((estado[-1], self.embedding_localidade(ids)), -1))


class AtencaoProjetada(nn.Module):
    """Multihead completa ou ProbSparse, tensores publicos (B,L,D)."""

    def __init__(self, d_model=16, cabecas=2, *, esparsa=False, causal=False,
                 fator=5, dropout=0.1):
        super().__init__()
        if d_model % cabecas:
            raise ValueError("d_model deve ser divisivel pelo numero de cabecas.")
        self.cabecas, self.d_head = cabecas, d_model // cabecas
        self.esparsa, self.causal, self.fator = esparsa, causal, fator
        self.dropout = dropout
        self.q = nn.Linear(d_model, d_model)
        self.k = nn.Linear(d_model, d_model)
        self.v = nn.Linear(d_model, d_model)
        self.saida = nn.Linear(d_model, d_model)

    def _separar(self, x: Tensor) -> Tensor:
        return x.reshape(x.shape[0], x.shape[1], self.cabecas, self.d_head).transpose(1, 2)

    def _probsparse(self, q: Tensor, k: Tensor, v: Tensor) -> Tensor:
        b, h, lq, d = q.shape
        lk = k.shape[2]
        sample_k = min(lk, max(1, self.fator * math.ceil(math.log(max(2, lk)))))
        top_q = min(lq, max(1, self.fator * math.ceil(math.log(max(2, lq)))))
        # Cada amostra ve os mesmos indices, independentemente de lote/ordem.
        # A semente local em eval nao consome nem altera o RNG global.
        gen = None
        if not self.training:
            gen = torch.Generator(device=q.device).manual_seed(0)
        indices = torch.randint(lk, (lq, sample_k), device=q.device, generator=gen)
        amostras = k[:, :, indices, :]
        escores_amostrados = torch.einsum("bhld,bhlsd->bhls", q, amostras)
        # Criterio max - soma/L_K utilizado pela implementacao de referencia.
        importancia = escores_amostrados.max(-1).values - escores_amostrados.sum(-1) / lk
        escolhidos = importancia.topk(top_q, dim=-1, sorted=False).indices
        consultas = q.gather(2, escolhidos[..., None].expand(b, h, top_q, d))
        escores = torch.matmul(consultas, k.transpose(-2, -1)) / math.sqrt(d)
        if self.causal:
            if lq != lk:
                raise ValueError("ProbSparse causal requer autoatencao.")
            mascara = torch.arange(lk, device=q.device)[None, None, None, :] > escolhidos[..., None]
            escores = escores.masked_fill(mascara, -torch.inf)
            contexto = v.cumsum(dim=2)
        else:
            contexto = v.mean(dim=2, keepdim=True).expand(b, h, lq, d).clone()
        # Como no codigo original, ProbSparse nao aplica dropout aos pesos;
        # dropout permanece nas conexoes residuais e no bloco feed-forward.
        atualizacao = torch.matmul(escores.softmax(dim=-1), v)
        return contexto.scatter(2, escolhidos[..., None].expand_as(atualizacao), atualizacao)

    def forward(self, consultas: Tensor, chaves: Tensor, valores: Tensor) -> Tensor:
        q, k, v = self._separar(self.q(consultas)), self._separar(self.k(chaves)), self._separar(self.v(valores))
        if self.esparsa:
            resultado = self._probsparse(q, k, v)
        else:
            resultado = F.scaled_dot_product_attention(
                q, k, v, dropout_p=self.dropout if self.training else 0.0,
                is_causal=self.causal,
            )
        resultado = resultado.transpose(1, 2).contiguous().flatten(2)
        return self.saida(resultado)


class BlocoEncoder(nn.Module):
    def __init__(self, *, esparsa: bool, d_model=16, d_ff=32, dropout=0.1):
        super().__init__()
        self.atencao = AtencaoProjetada(d_model, esparsa=esparsa, dropout=dropout)
        self.ff = nn.Sequential(nn.Linear(d_model, d_ff), nn.ReLU(), nn.Dropout(dropout), nn.Linear(d_ff, d_model))
        self.norm1, self.norm2 = nn.LayerNorm(d_model), nn.LayerNorm(d_model)
        self.drop = nn.Dropout(dropout)

    def forward(self, x: Tensor) -> Tensor:
        x = self.norm1(x + self.drop(self.atencao(x, x, x)))
        return self.norm2(x + self.drop(self.ff(x)))


class BlocoDecoder(nn.Module):
    def __init__(self, *, esparsa: bool, d_model=16, d_ff=32, dropout=0.1):
        super().__init__()
        self.autoatencao = AtencaoProjetada(d_model, esparsa=esparsa, causal=True, dropout=dropout)
        self.cruzada = AtencaoProjetada(d_model, dropout=dropout)
        self.ff = nn.Sequential(nn.Linear(d_model, d_ff), nn.ReLU(), nn.Dropout(dropout), nn.Linear(d_ff, d_model))
        self.norm1, self.norm2, self.norm3 = (nn.LayerNorm(d_model) for _ in range(3))
        self.drop = nn.Dropout(dropout)

    def forward(self, x: Tensor, memoria: Tensor) -> Tensor:
        x = self.norm1(x + self.drop(self.autoatencao(x, x, x)))
        x = self.norm2(x + self.drop(self.cruzada(x, memoria, memoria)))
        return self.norm3(x + self.drop(self.ff(x)))


class Distilacao(nn.Module):
    def __init__(self, d_model=16):
        super().__init__()
        self.rede = nn.Sequential(
            nn.Conv1d(d_model, d_model, 3, padding=1, padding_mode="circular"),
            nn.BatchNorm1d(d_model), nn.ELU(), nn.MaxPool1d(3, stride=2, padding=1),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.rede(x.transpose(1, 2)).transpose(1, 2)


class TransformerDireto(nn.Module):
    """Encoder-decoder vanilla completo; Informer habilita os 3 componentes.

    Decoder recebe a metade final do contexto e zeros para todo o futuro.
    Nem durante o treino recebe y ou covariaveis futuras.
    """

    def __init__(self, seq_len: int, pred_len: int, num_localidades: int, *, informer=False):
        super().__init__()
        self.seq_len, self.pred_len, self.informer = seq_len, pred_len, informer
        self.label_len = max(1, seq_len // 2)
        d_model = 16
        self.projecao_encoder, self.projecao_decoder = nn.Linear(1, d_model), nn.Linear(1, d_model)
        self.embedding_localidade = nn.Embedding(num_localidades, 8)
        self.projecao_localidade = nn.Linear(8, d_model)
        self.encoders = nn.ModuleList([BlocoEncoder(esparsa=informer) for _ in range(2)])
        self.distilacao = Distilacao() if informer else nn.Identity()
        self.norm_encoder, self.norm_decoder = nn.LayerNorm(d_model), nn.LayerNorm(d_model)
        self.decoder = BlocoDecoder(esparsa=informer)
        self.saida = nn.Linear(d_model, 1)
        self.drop = nn.Dropout(0.1)
        pos = torch.arange(seq_len + pred_len, dtype=torch.float32)[:, None]
        taxa = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(seq_len + pred_len, d_model)
        pe[:, 0::2], pe[:, 1::2] = torch.sin(pos * taxa), torch.cos(pos * taxa)
        self.register_buffer("posicao", pe)

    def entrada_decoder(self, x: Tensor) -> Tensor:
        if x.ndim == 2:
            x = x.unsqueeze(-1)
        return torch.cat((x[:, -self.label_len:, :], x.new_zeros(len(x), self.pred_len, 1)), dim=1)

    def forward(self, x: Tensor, ids: Tensor) -> Tensor:
        if x.ndim == 2:
            x = x.unsqueeze(-1)
        if x.shape[1:] != (self.seq_len, 1):
            raise ValueError("Contexto Transformer/Informer incompatível.")
        local = self.projecao_localidade(self.embedding_localidade(ids))[:, None, :]
        memoria = self.drop(self.projecao_encoder(x) + self.posicao[:self.seq_len] + local)
        memoria = self.encoders[0](memoria)
        memoria = self.norm_encoder(self.encoders[1](self.distilacao(memoria)))
        entrada = self.entrada_decoder(x)
        pos = self.posicao[self.seq_len - self.label_len:self.seq_len + self.pred_len]
        dec = self.drop(self.projecao_decoder(entrada) + pos + local)
        dec = self.norm_decoder(self.decoder(dec, memoria))
        return self.saida(dec[:, -self.pred_len:, :]).squeeze(-1)


def criar_baseline(modelo: str, seq_len: int, pred_len: int, num_localidades: int) -> nn.Module:
    if modelo == "GRU":
        return GRUDireta(seq_len, pred_len, num_localidades)
    if modelo in {"Transformer", "Informer"}:
        return TransformerDireto(seq_len, pred_len, num_localidades, informer=modelo == "Informer")
    raise ValueError(f"Baseline neural desconhecido: {modelo}")
