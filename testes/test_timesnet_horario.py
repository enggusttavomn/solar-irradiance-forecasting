"""Testes rapidos em CPU para o TimesNet horario multistep."""

from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")

from codigo_fonte.timesnet_horario import (  # noqa: E402
    InceptionBlock2D,
    TimesBlock,
    TimesNetHorario,
    fft_top_k_periods,
)


def test_fft_detecta_periodo_diario_sem_selecionar_frequencia_zero() -> None:
    horas = torch.arange(336, dtype=torch.float32)
    ciclo_diario = torch.sin(2.0 * math.pi * horas / 24.0)
    # O termo constante domina o espectro bruto. Se DC participasse do top-k,
    # o calculo do periodo seria invalido em vez de identificar 24 horas.
    x = torch.stack((1_000.0 + ciclo_diario, 2_000.0 + 2 * ciclo_diario))
    x = x.unsqueeze(-1)

    periodos, amplitudes = fft_top_k_periods(x, top_k=1)

    assert periodos.tolist() == [[24], [24]]
    assert amplitudes.shape == (2, 1)
    assert torch.all(amplitudes > 0)


def test_fft_seleciona_periodos_independentemente_por_amostra() -> None:
    horas = torch.arange(336, dtype=torch.float32)
    ciclo_diario = torch.sin(2.0 * math.pi * horas / 24.0)
    ciclo_semanal = torch.sin(2.0 * math.pi * horas / 168.0)
    x = torch.stack((ciclo_diario, ciclo_semanal)).unsqueeze(-1)

    periodos, _ = fft_top_k_periods(x, top_k=1)

    assert periodos.tolist() == [[24], [168]]


def test_inception_usa_multiplos_kernels_e_preserva_a_grade() -> None:
    camada = InceptionBlock2D(3, 5, num_kernels=3)
    x = torch.randn(2, 3, 4, 6)

    saida = camada(x)

    assert camada.tamanhos_kernel == (1, 3, 5)
    assert saida.shape == (2, 5, 4, 6)


def test_timesblock_faz_reshape_periodico_agregacao_e_residual() -> None:
    bloco = TimesBlock(
        comprimento=48,
        d_model=4,
        d_ff=6,
        top_k=2,
        num_kernels=2,
    )
    # Zerar apenas o ramo convolucional permite testar exatamente a conexao
    # residual, independentemente dos periodos escolhidos pela FFT.
    with torch.no_grad():
        for parametro in bloco.convolucao.parameters():
            parametro.zero_()
    x = torch.randn(2, 48, 4, requires_grad=True)

    saida = bloco(x)
    saida.sum().backward()

    assert saida.shape == x.shape
    assert torch.allclose(saida, x)
    assert x.grad is not None
    assert torch.allclose(x.grad, torch.ones_like(x))


def test_timesnet_padrao_projeta_336_horas_em_72_saidas() -> None:
    modelo = TimesNetHorario(
        d_model=4,
        d_ff=8,
        num_blocos=1,
        top_k=2,
        num_kernels=2,
        dropout=0.0,
    )
    x = torch.randn(2, 336)

    previsao = modelo(x)
    previsao.mean().backward()

    assert modelo.projecao_temporal.in_features == 336
    assert modelo.projecao_temporal.out_features == 72
    assert previsao.shape == (2, 72)
    assert torch.isfinite(previsao).all()
    assert modelo.projecao_temporal.weight.grad is not None


def test_timesnet_preserva_previsao_ao_mudar_companheiros_do_lote() -> None:
    torch.manual_seed(123)
    horas = torch.arange(24, dtype=torch.float32)
    ancora = torch.sin(2.0 * math.pi * horas / 6.0)
    ancora = ancora + 0.2 * torch.sin(2.0 * math.pi * horas / 5.0)
    companheiro_a = torch.sin(2.0 * math.pi * horas / 12.0)
    companheiro_b = torch.sin(2.0 * math.pi * horas / 3.0)
    lote_a = torch.stack((ancora, companheiro_a, companheiro_a, companheiro_a))
    lote_b = torch.stack((ancora, companheiro_b, companheiro_b, companheiro_b))
    ids = torch.zeros(4, dtype=torch.long)

    modelo = TimesNetHorario(
        seq_len=24,
        pred_len=6,
        d_model=2,
        d_ff=4,
        num_blocos=1,
        top_k=2,
        num_kernels=1,
        num_localidades=1,
        dropout=0.0,
    ).eval()

    with torch.no_grad():
        previsao_a = modelo(lote_a, ids)[0]
        previsao_b = modelo(lote_b, ids)[0]
        previsao_isolada = modelo(ancora.unsqueeze(0), ids[:1])[0]

    assert torch.allclose(previsao_a, previsao_b, rtol=1e-6, atol=1e-6)
    assert torch.allclose(previsao_a, previsao_isolada, rtol=1e-6, atol=1e-6)


def test_timesnet_aceita_canal_univariado_e_embedding_de_localidade() -> None:
    modelo = TimesNetHorario(
        seq_len=24,
        pred_len=6,
        d_model=4,
        d_ff=8,
        num_blocos=1,
        top_k=2,
        num_kernels=2,
        num_localidades=3,
        dropout=0.0,
    )
    x = torch.randn(2, 24, 1)
    ids = torch.tensor([0, 2])

    previsao = modelo(x, ids)

    assert previsao.shape == (2, 6)
    assert modelo.embedding_localidade is not None
    assert modelo.embedding_localidade.weight.shape == (3, 4)


def test_timesnet_rejeita_formas_valores_e_localidades_invalidas() -> None:
    modelo = TimesNetHorario(
        seq_len=24,
        pred_len=6,
        d_model=4,
        d_ff=8,
        num_blocos=1,
        top_k=2,
        num_kernels=1,
        num_localidades=2,
    )

    with pytest.raises(ValueError, match="forma"):
        modelo(torch.randn(2, 23), torch.tensor([0, 1]))
    with pytest.raises(ValueError, match="nao finitos"):
        modelo(
            torch.full((2, 24), float("nan")),
            torch.tensor([0, 1]),
        )
    with pytest.raises(ValueError, match="obrigatorio"):
        modelo(torch.randn(2, 24))
    with pytest.raises(ValueError, match="fora do intervalo"):
        modelo(torch.randn(2, 24), torch.tensor([0, 2]))

    sem_localidade = TimesNetHorario(
        seq_len=24,
        pred_len=6,
        d_model=4,
        d_ff=8,
        num_blocos=1,
        top_k=2,
        num_kernels=1,
    )
    with pytest.raises(ValueError, match="num_localidades"):
        sem_localidade(torch.randn(2, 24), torch.tensor([0, 1]))


@pytest.mark.parametrize(
    ("argumento", "valor"),
    [
        ("seq_len", 1),
        ("pred_len", 0),
        ("top_k", 13),
        ("num_localidades", 0),
        ("dropout", 1.0),
    ],
)
def test_timesnet_valida_hiperparametros(argumento: str, valor: object) -> None:
    kwargs = {
        "seq_len": 24,
        "pred_len": 6,
        "d_model": 4,
        "d_ff": 8,
        "num_blocos": 1,
        "top_k": 2,
        "num_kernels": 1,
    }
    kwargs[argumento] = valor

    with pytest.raises(ValueError):
        TimesNetHorario(**kwargs)
