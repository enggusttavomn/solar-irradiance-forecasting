"""Verifica a busca mensal isolada da TimesNet e suas salvaguardas de protocolo."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn

import codigo_fonte.experimentos.otimizacao_timesnet_mensal as otim
from codigo_fonte.experimentos.experimento_multirresolucao import ConfiguracaoMultirresolucao, JanelasDiretas, PASTA_RESULTADOS, SerieResolucao, TAREFAS_CANONICAS

# Deslocamento fisico aplicado pela previsao falsa na primeira semente; a segunda
# recebe o simetrico dividido por tres, de modo que o ensemble nunca coincide com
# a media dos MAEs por semente.
DESLOCAMENTOS = {"mse": 9.0, "huber": 6.0, "mae": 3.0}
SEMENTES = (11, 23)


def _serie(localidade_id: int, caminho: Path, fim: str = "2024-12-31") -> SerieResolucao:
    datas = pd.date_range("2019-01-31", fim, freq="ME")
    meses = np.asarray(datas.month, dtype=float)
    anos = np.asarray(datas.year, dtype=float)
    nivel = 150.0 + 100.0 * localidade_id
    # A componente que varia entre anos e deterministica, mas impede que a
    # climatologia reproduza a serie exatamente e zere todos os desvios.
    interanual = 12.0 * np.sin(1.7 * (anos - 2019.0) + 0.6 * meses + localidade_id)
    ghi = nivel + 40.0 * np.sin(2 * np.pi * (meses - 1) / 12) + interanual + localidade_id
    return SerieResolucao(
        localidade=f"Fabrica {localidade_id}",
        localidade_id=localidade_id,
        pais="Brasil",
        datas=pd.DatetimeIndex(datas),
        ghi=ghi.astype(np.float32),
        frequencia="ME",
        caminho_fonte=caminho,
    )


@pytest.fixture
def series(tmp_path: Path) -> tuple[SerieResolucao, ...]:
    caminho = tmp_path / "fonte.csv"
    caminho.write_text("data,ghi\n2019-01-31,150\n", encoding="utf-8")
    return tuple(_serie(i, caminho) for i in range(2))


def _config(**alteracoes) -> ConfiguracaoMultirresolucao:
    return replace(
        ConfiguracaoMultirresolucao(sementes=SEMENTES, max_epocas_mensal=3, paciencia_mensal=1),
        **alteracoes,
    )


def _candidatos() -> tuple[otim.Candidato, ...]:
    return (
        otim.Candidato("referencia_mse"),
        otim.Candidato("huber", perda="huber"),
        otim.Candidato("mae", perda="mae"),
    )


class _RedeMarcada(nn.Module):
    """Rede minima que apenas carrega o deslocamento usado pela previsao falsa."""

    def __init__(self, deslocamento: float) -> None:
        super().__init__()
        self.deslocamento = float(deslocamento)
        self.peso = nn.Parameter(torch.tensor(deslocamento))

    def forward(self, x, ids):  # pragma: no cover - a previsao e substituida
        raise AssertionError("A previsao deveria ter sido substituida no teste.")


@pytest.fixture
def treino_falso(monkeypatch) -> list[dict[str, object]]:
    """Substitui treino e previsao por um deslocamento fisico deterministico."""

    registros: list[dict[str, object]] = []

    def treinar(*, tarefa, configuracao, semente, ajuste, escalas, validacao=None,
                perda="mse", epocas_fixas=None, deslocamento_validacao=None):
        registros.append({
            "perda": perda, "semente": int(semente), "seq_len": tarefa.seq_len,
            "epocas_fixas": epocas_fixas, "particao": ajuste.particao,
            "deslocamento_recebido": deslocamento_validacao is not None,
            "ajuste_tem_negativos": bool((ajuste.y_bruto < 0).any()),
            "ultimo_alvo_ajuste": pd.Timestamp(ajuste.datas_alvo.max()),
            "ultimo_alvo_validacao": (None if validacao is None
                                      else pd.Timestamp(validacao.datas_alvo.max())),
            "d_model": configuracao.timesnet_d_model,
            "taxa_aprendizado": configuracao.taxa_aprendizado,
        })
        base = DESLOCAMENTOS[perda]
        deslocamento = base if int(semente) == SEMENTES[0] else -base / 3
        historico = pd.DataFrame({"epoca": [1], "perda_treino": [0.5], "mae_validacao_wm2": [1.0]})
        return _RedeMarcada(deslocamento), 7 + int(semente), historico

    monkeypatch.setattr(otim, "treinar_candidato", treinar)
    monkeypatch.setattr(
        otim, "_prever",
        lambda modelo, janelas, escalas, config: janelas.y_bruto.astype(float) + modelo.deslocamento,
    )
    return registros


def _janelas_simples() -> JanelasDiretas:
    ids = np.asarray([0, 0, 0, 1], dtype=np.int64)
    y = np.where(ids == 0, 20.0, 200.0).astype(np.float32).reshape(-1, 1)
    datas = pd.date_range("2024-01-31", periods=len(ids), freq="ME")
    return JanelasDiretas(
        x_bruto=np.repeat(y, 12, axis=1), y_bruto=y, localidade_id=ids,
        localidade=np.asarray([f"Fabrica {i}" for i in ids], dtype=object),
        origem=datas, datas_alvo=datas.to_numpy().reshape(-1, 1),
        seq_len=12, pred_len=1, particao="teste",
    )


@pytest.mark.parametrize(
    "alteracao",
    [
        {"nome": "nome invalido"},
        {"nome": ""},
        {"perda": "quantil"},
        {"seq_len": 6},
        {"d_model": 7},
        {"blocos": 0},
        {"taxa_aprendizado": 0.0},
        {"dropout": 1.0},
        {"alvo": "residuo"},
    ],
)
def test_candidato_rejeita_configuracao_invalida(alteracao) -> None:
    with pytest.raises(ValueError):
        otim.Candidato(**{"nome": "teste", **alteracao})


def test_candidato_aplica_apenas_hiperparametros_da_rede() -> None:
    config = otim.Candidato("mae_dim16", perda="mae", d_model=16, d_ff=32,
                            taxa_aprendizado=3e-4).configurar(_config())
    assert (config.timesnet_d_model, config.timesnet_d_ff) == (16, 32)
    assert config.taxa_aprendizado == pytest.approx(3e-4)
    assert config.sementes == SEMENTES  # nada alem da rede e alterado


def test_adaptar_tarefa_desloca_ajuste_e_preserva_validacao_e_teste(series) -> None:
    tarefa = otim.adaptar_tarefa(TAREFAS_CANONICAS["monthly_1"], series, 24)
    assert tarefa.seq_len == 24
    # Com historico desde 2019-01, o contexto de 24 meses so admite origens a partir de 2021-01.
    assert tarefa.ajuste.inicio_origem == "2021-01-31"
    assert tarefa.ajuste.origens_esperadas_por_localidade == 24
    assert tarefa.refit.inicio_origem == "2021-01-31"
    assert tarefa.refit.origens_esperadas_por_localidade == 36
    assert tarefa.validacao == TAREFAS_CANONICAS["monthly_1"].validacao
    assert tarefa.teste == TAREFAS_CANONICAS["monthly_1"].teste


def test_adaptar_tarefa_recusa_contexto_sem_origens_suficientes(series) -> None:
    with pytest.raises(ValueError, match="apenas 12 origens"):
        otim.adaptar_tarefa(TAREFAS_CANONICAS["monthly_1"], series, 36)


@pytest.mark.parametrize(
    "argumentos",
    [
        {"tarefa": TAREFAS_CANONICAS["daily_30"], "seq_len": 12},
        {"seq_len": 12, "minimo_origens": 0},
        {"seq_len": 12, "inicio_ajuste": "2020-01-15"},
        {"seq_len": 999},
    ],
)
def test_adaptar_tarefa_rejeita_pedidos_invalidos(series, argumentos) -> None:
    parametros = {"tarefa": TAREFAS_CANONICAS["monthly_1"], **argumentos}
    with pytest.raises(ValueError):
        otim.adaptar_tarefa(parametros.pop("tarefa"), series, **parametros)


def test_climatologia_da_anomalia_coincide_com_a_baseline(series) -> None:
    """A parcela somada de volta e exatamente a baseline Climatologia do projeto."""
    tarefa = TAREFAS_CANONICAS["monthly_6"]
    janelas = otim.base.construir_janelas(
        series, seq_len=tarefa.seq_len, pred_len=tarefa.pred_len,
        intervalo=tarefa.teste, particao="teste")
    tabela = otim.climatologia_mensal(series, fim_exclusivo="2024-01-01")
    _, alvo = otim.climatologia_nas_janelas(janelas, tabela)
    esperado = otim.base.prever_climatologia(janelas, series,
                                             fim_ajuste_exclusivo="2024-01-01")
    np.testing.assert_allclose(alvo, esperado, rtol=0, atol=1e-9)


def test_climatologia_do_contexto_recupera_os_meses_anteriores_a_origem(series) -> None:
    tarefa = TAREFAS_CANONICAS["monthly_1"]
    janelas = otim.base.construir_janelas(
        series, seq_len=tarefa.seq_len, pred_len=tarefa.pred_len,
        intervalo=tarefa.teste, particao="teste")
    tabela = otim.climatologia_mensal(series, fim_exclusivo="2024-01-01")
    contexto, _ = otim.climatologia_nas_janelas(janelas, tabela)
    # O contexto cobre os doze meses que antecedem a origem, entao o ultimo dele
    # corresponde ao mes anterior e o primeiro fecha o ciclo no mesmo mes da origem.
    linha = 0
    origem = janelas.origem[linha]
    identificador = int(janelas.localidade_id[linha])
    anterior = (origem - pd.DateOffset(months=1)).month
    assert contexto[linha, -1] == pytest.approx(tabela[identificador][anterior - 1])
    assert contexto[linha, 0] == pytest.approx(tabela[identificador][origem.month - 1])
    assert contexto.shape == (len(janelas.x_bruto), tarefa.seq_len)


def test_climatologia_ignora_dados_posteriores_ao_corte(series) -> None:
    curta = tuple(_serie(i, series[0].caminho_fonte, fim="2022-12-31") for i in range(2))
    tabela_corte = otim.climatologia_mensal(series, fim_exclusivo="2023-01-01")
    tabela_curta = otim.climatologia_mensal(curta, fim_exclusivo="2023-01-01")
    for identificador, valores in tabela_corte.items():
        np.testing.assert_allclose(valores, tabela_curta[identificador], rtol=0, atol=1e-9)


def test_preparar_treino_devolve_desvios_que_reconstroem_o_ghi(series) -> None:
    tarefa = TAREFAS_CANONICAS["monthly_1"]
    ajuste = otim.base.construir_janelas(series, seq_len=12, pred_len=1,
                                         intervalo=tarefa.ajuste, particao="ajuste")
    validacao = otim.base.construir_janelas(series, seq_len=12, pred_len=1,
                                            intervalo=tarefa.validacao, particao="validacao")
    candidato = otim.Candidato("anomalia_mae", perda="mae", alvo="anomalia")
    ajuste_anom, val_anom, escalas, deslocamento = otim.preparar_treino(
        candidato, series, ajuste, validacao,
        fim_exclusivo="2023-01-01", nome_ajuste="selecao")

    np.testing.assert_allclose(val_anom.y_bruto + deslocamento, validacao.y_bruto,
                               rtol=0, atol=1e-4)
    assert (ajuste_anom.y_bruto < 0).any(), "desvios devem ser negativos em parte do ano"
    assert ajuste_anom.x_bruto.shape == ajuste.x_bruto.shape
    # As escalas precisam cobrir o intervalo real dos desvios de ajuste.
    assert (escalas["amplitude_escala_wm2"] > 0).all()
    assert set(escalas["fim_exclusivo"]) == {pd.Timestamp("2023-01-01").isoformat()}
    assert sorted(escalas["localidade_id"]) == [0, 1]


def test_preparar_treino_no_alvo_bruto_nao_altera_nada(series) -> None:
    tarefa = TAREFAS_CANONICAS["monthly_1"]
    ajuste = otim.base.construir_janelas(series, seq_len=12, pred_len=1,
                                         intervalo=tarefa.ajuste, particao="ajuste")
    validacao = otim.base.construir_janelas(series, seq_len=12, pred_len=1,
                                            intervalo=tarefa.validacao, particao="validacao")
    saida = otim.preparar_treino(otim.Candidato("referencia_mse"), series, ajuste, validacao,
                                 fim_exclusivo="2023-01-01", nome_ajuste="selecao")
    assert saida[0] is ajuste and saida[1] is validacao and saida[3] is None


def test_macro_mae_pesa_localidades_igualmente_e_aplica_piso_zero() -> None:
    janelas = _janelas_simples()
    # Erros por ponto: 10, 10, 10 na primeira fabrica e 200 na segunda.
    previsto = np.array([[10.0], [30.0], [10.0], [-50.0]])
    assert otim.macro_mae(janelas, previsto) == pytest.approx(105.0)


@pytest.mark.parametrize("previsto", [np.zeros(4), np.full((4, 1), np.nan)])
def test_macro_mae_rejeita_previsao_invalida(previsto) -> None:
    with pytest.raises(ValueError):
        otim.macro_mae(_janelas_simples(), previsto)


def test_selecao_escolhe_menor_mae_de_ensemble_sem_tocar_em_2024(
    tmp_path, series, treino_falso
) -> None:
    congelado = otim.selecionar(
        series=series, tarefa=TAREFAS_CANONICAS["monthly_1"], candidatos=_candidatos(),
        configuracao=_config(), pasta=tmp_path,
    )
    assert congelado["vencedor"]["nome"] == "mae"
    assert congelado["selecao_concluida_antes_do_teste"] is True
    # Deslocamentos 3 e -1 produzem ensemble de 1 W/m2 e media por semente de 2 W/m2.
    assert congelado["vencedor"]["MAE_validacao_ensemble_wm2"] == pytest.approx(1.0)
    assert congelado["vencedor"]["MAE_validacao_media_sementes_wm2"] == pytest.approx(2.0)
    assert congelado["vencedor"]["epocas"] == {"11": 18, "23": 30}

    ranking = pd.read_csv(tmp_path / "ranking_validacao.csv")
    assert list(ranking["nome"]) == ["mae", "huber", "referencia_mse"]
    assert ranking["MAE_validacao_ensemble_wm2"].is_monotonic_increasing
    assert list(ranking["origens_ajuste_por_local"]) == [36, 36, 36]
    assert list(ranking["origens_validacao_por_local"]) == [12, 12, 12]

    previsoes = pd.read_csv(tmp_path / "previsoes_validacao.csv", parse_dates=["data_alvo"])
    assert previsoes["data_alvo"].max() < pd.Timestamp("2024-01-01")
    assert not (tmp_path / "previsoes_teste.csv").exists()
    for registro in treino_falso:
        assert registro["ultimo_alvo_ajuste"] < pd.Timestamp("2023-01-01")
        assert registro["ultimo_alvo_validacao"] < pd.Timestamp("2024-01-01")
    assert len(treino_falso) == len(_candidatos()) * len(SEMENTES)


def test_alvo_anomalia_reconstroi_o_mesmo_ghi_do_alvo_bruto(
    tmp_path, series, treino_falso
) -> None:
    """Com o mesmo erro de previsao, os dois alvos tem de dar o mesmo MAE em GHI.

    A previsao falsa erra por um deslocamento fixo no espaco em que a rede
    trabalha. Se a soma da climatologia estivesse errada, o candidato de
    anomalia acumularia um erro diferente.
    """
    candidatos = (otim.Candidato("mae", perda="mae"),
                  otim.Candidato("anomalia_mae", perda="mae", alvo="anomalia"))
    otim.selecionar(series=series, tarefa=TAREFAS_CANONICAS["monthly_1"],
                    candidatos=candidatos, configuracao=_config(), pasta=tmp_path)
    ranking = pd.read_csv(tmp_path / "ranking_validacao.csv").set_index("nome")
    assert ranking.loc["anomalia_mae", "MAE_validacao_ensemble_wm2"] == pytest.approx(
        ranking.loc["mae", "MAE_validacao_ensemble_wm2"], abs=1e-3)
    assert set(ranking["alvo"]) == {"bruto", "anomalia"}
    # O candidato de anomalia guarda as escalas dos desvios, que sao proprias dele.
    escalas = pd.read_csv(tmp_path / "candidatos" / "anomalia_mae" / "escalas.csv")
    assert set(escalas["ajuste"]) == {"selecao"}
    assert not (tmp_path / "candidatos" / "mae" / "escalas.csv").exists()


def test_alvo_anomalia_treina_sobre_desvios_e_nao_sobre_ghi(
    tmp_path, series, treino_falso
) -> None:
    candidato = otim.Candidato("anomalia_mae", perda="mae", alvo="anomalia")
    otim.selecionar(series=series, tarefa=TAREFAS_CANONICAS["monthly_1"],
                    candidatos=(candidato,), configuracao=_config(), pasta=tmp_path)
    assert treino_falso, "o treino deveria ter sido chamado"
    for registro in treino_falso:
        assert registro["deslocamento_recebido"] is True
        assert registro["ajuste_tem_negativos"] is True


def test_selecao_usa_escalas_ajustadas_antes_da_validacao(tmp_path, series, treino_falso) -> None:
    otim.selecionar(series=series, tarefa=TAREFAS_CANONICAS["monthly_1"],
                    candidatos=_candidatos()[:1], configuracao=_config(), pasta=tmp_path)
    escalas = pd.read_csv(tmp_path / "escalas_selecao.csv")
    assert set(escalas["fim_exclusivo"]) == {pd.Timestamp("2023-01-01").isoformat()}
    assert set(escalas["ajuste"]) == {"selecao"}


def test_selecao_registra_candidato_sem_historico(tmp_path, series, treino_falso) -> None:
    candidatos = (otim.Candidato("mae", perda="mae"), otim.Candidato("contexto36", seq_len=36))
    congelado = otim.selecionar(series=series, tarefa=TAREFAS_CANONICAS["monthly_1"],
                                candidatos=candidatos, configuracao=_config(), pasta=tmp_path)
    descartados = json.loads((tmp_path / "candidatos_descartados.json").read_text(encoding="utf-8"))
    assert [d["candidato"] for d in descartados] == ["contexto36"]
    assert congelado["vencedor"]["nome"] == "mae"


def test_selecao_falha_quando_nenhum_candidato_e_admissivel(tmp_path, series, treino_falso) -> None:
    with pytest.raises(ValueError, match="Nenhum candidato"):
        otim.selecionar(series=series, tarefa=TAREFAS_CANONICAS["monthly_1"],
                        candidatos=(otim.Candidato("contexto36", seq_len=36),),
                        configuracao=_config(), pasta=tmp_path)


def test_refit_do_vencedor_repete_as_epocas_congeladas(tmp_path, series, treino_falso) -> None:
    candidato = otim.Candidato("mae", perda="mae")
    congelado = otim.selecionar(series=series, tarefa=TAREFAS_CANONICAS["monthly_1"],
                                candidatos=(candidato,), configuracao=_config(),
                                pasta=tmp_path / "selecao")
    treino_falso.clear()
    mae_teste = otim.avaliar_vencedor(
        series=series, tarefa=TAREFAS_CANONICAS["monthly_1"], candidato=candidato,
        configuracao=_config(), pasta=tmp_path / "teste",
        epocas=congelado["vencedor"]["epocas"],
    )
    assert mae_teste == pytest.approx(1.0)
    assert [r["epocas_fixas"] for r in treino_falso] == [18, 30]
    assert all(r["ultimo_alvo_validacao"] is None for r in treino_falso)
    assert all(r["ultimo_alvo_ajuste"] < pd.Timestamp("2024-01-01") for r in treino_falso)
    escalas = pd.read_csv(tmp_path / "teste" / "escalas_refit.csv")
    assert set(escalas["fim_exclusivo"]) == {pd.Timestamp("2024-01-01").isoformat()}
    macro = pd.read_csv(tmp_path / "teste" / "metricas_macro.csv")
    assert set(macro["particao"]) == {"teste_2024"}
    assert {"TimesNet", "Climatologia", "Persistencia", "Sazonal ingenuo"} <= set(macro["modelo"])


def test_contrato_distingue_conjuntos_de_candidatos(series) -> None:
    argumentos = (series, _candidatos(), _config(), "monthly_1", 18, "2020-01-31")
    contrato = otim._contrato(*argumentos)
    outro = otim._contrato(series, _candidatos()[:2], *argumentos[2:])
    assert contrato["sha256_contrato"] != outro["sha256_contrato"]
    assert contrato["quantizacao"] is False
    assert contrato["sha256_contrato"] == otim._contrato(*argumentos)["sha256_contrato"]


@pytest.mark.parametrize(
    "destino",
    ["avaliacao_multirresolucao_corrigida_v2", "avaliacao_multirresolucao",
     "avaliacao_horaria_timesnet_corrigida_retomavel", "avaliacao_multirresolucao/subpasta"],
)
def test_executar_recusa_sobrescrever_resultados_canonicos(monkeypatch, series, destino) -> None:
    monkeypatch.setattr(otim.base, "carregar_series_diarias",
                        lambda pasta=None: ((), pd.DataFrame()))
    monkeypatch.setattr(otim.base, "agregar_series_mensais", lambda diarias: series)
    with pytest.raises(ValueError, match="pasta nova"):
        otim.executar(pasta_saida=Path(PASTA_RESULTADOS) / destino, configuracao=_config())


@pytest.mark.parametrize(
    "alteracao",
    [{"tarefas": ("daily_30",)}, {"tarefas": ()}, {"candidatos": ()}],
)
def test_executar_rejeita_tarefas_e_candidatos_invalidos(tmp_path, alteracao) -> None:
    parametros = {"pasta_saida": tmp_path / "busca", "configuracao": _config(),
                  "candidatos": _candidatos(), **alteracao}
    with pytest.raises(ValueError):
        otim.executar(**parametros)


@pytest.fixture
def executar_sem_treino(monkeypatch, series):
    """Permite exercitar a orquestracao de `executar` sem treinar nenhuma rede."""

    monkeypatch.setattr(otim.base, "carregar_series_diarias",
                        lambda pasta=None: ((), pd.DataFrame([{"localidade": "Fabrica 0"}])))
    monkeypatch.setattr(otim.base, "agregar_series_mensais", lambda diarias: series)
    monkeypatch.setattr(
        otim, "selecionar",
        lambda **k: {"vencedor": {"nome": "mae", "MAE_validacao_ensemble_wm2": 1.0,
                                  "epocas": {"11": 18, "23": 30}}},
    )


def test_executar_grava_resumo_e_libera_o_lock(tmp_path, executar_sem_treino) -> None:
    pasta = tmp_path / "busca"
    resumo = otim.executar(pasta_saida=pasta, tarefas=("monthly_1",),
                           candidatos=_candidatos(), configuracao=_config())
    assert resumo == [{"tarefa": "monthly_1", "candidato": "mae", "MAE_validacao_wm2": 1.0,
                       "modo": "completa", "teste_avaliado": False}]
    assert not (pasta / "monthly_1" / "execucao.lock").exists()
    assert (pasta / "resumo.csv").is_file()
    status = json.loads((pasta / "monthly_1" / "status_execucao.json").read_text(encoding="utf-8"))
    assert status["etapa"] == "concluida"


def test_executar_recusa_retomar_pasta_com_lock_pendente(tmp_path, executar_sem_treino) -> None:
    pasta = tmp_path / "busca"
    otim.executar(pasta_saida=pasta, tarefas=("monthly_1",), candidatos=_candidatos(),
                  configuracao=_config())
    (pasta / "monthly_1" / "execucao.lock").write_text("4242", encoding="utf-8")
    with pytest.raises(RuntimeError, match="apague o arquivo"):
        otim.executar(pasta_saida=pasta, tarefas=("monthly_1",), candidatos=_candidatos(),
                      configuracao=_config())


def test_executar_rejeita_candidatos_com_nomes_repetidos(tmp_path) -> None:
    with pytest.raises(ValueError, match="nomes unicos"):
        otim.executar(pasta_saida=tmp_path / "busca", configuracao=_config(),
                      candidatos=(otim.Candidato("mae"), otim.Candidato("mae")))


def test_grade_padrao_otimiza_somente_timesnet_pura():
    candidatos = otim.candidatos_padrao()
    assert len(candidatos) == 9
    assert {c.alvo for c in candidatos} == {"bruto"}
    assert {c.perda for c in candidatos} == {"mse", "mae", "huber"}
    assert {c.seq_len for c in candidatos} == {12, 24, 36}
    assert all("anomalia" not in c.nome for c in candidatos)


@pytest.mark.parametrize("alvo", ["bruto", "anomalia"])
def test_contrato_descreve_somente_preprocessamento_dos_candidatos(series, alvo):
    candidato = otim.Candidato("teste", alvo=alvo)
    contrato = otim._contrato(series, (candidato,), _config(), "monthly_1", 18, "2020-01-31")
    assert bool(contrato.get("climatologia_anomalia")) == (alvo == "anomalia")
    assert any("soma de volta" in nota for nota in contrato["limitacoes"]) == (alvo == "anomalia")


def test_novo_contrato_puro_aceito_na_comparacao_principal(series):
    from dataclasses import asdict
    from codigo_fonte.analises_e_relatorios.gerar_tabela_resultados_ghi_otimizada import validar_mensal_pura
    cfg = ConfiguracaoMultirresolucao()
    candidatos = otim.candidatos_padrao()
    contrato = otim._contrato(series, candidatos, cfg, "monthly_1", 18, "2020-01-31")
    vencedor = {**asdict(candidatos[0]), "epocas": {str(s): 10 for s in cfg.sementes}}
    validar_mensal_pura("monthly_1", {"tarefa": {"slug": "monthly_1"}, "vencedor": vencedor}, contrato)
