"""Contratos, congelamento temporal e metricas da quantizacao horaria/diaria."""

from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch

from codigo_fonte import experimento_quantizacao_resolucoes as exp


def _json(path, obj):
    exp.base.salvar_json_atomico(obj, path)


def _contexto(horaria=False):
    fonte = exp.base.TAREFA_HORARIA_EXTENSAO if horaria else exp.base.TAREFAS_CANONICAS["daily_30"]
    tarefa = replace(fonte, seq_len=12, pred_len=2, horizontes=(1, 2))
    ids = np.array([0, 0, 1], dtype=np.int64)
    metadados = dict(x_bruto=np.linspace(8, 220, 36, dtype=np.float32).reshape(3, 12),
                    y_bruto=np.array([[2., 3.], [4., 9.], [20., 21.]], dtype=np.float32),
                    localidade_id=ids, localidade=np.array(["A", "A", "B"]),
                    seq_len=12, pred_len=2, particao="validacao_2023")
    datas = pd.date_range("2023-01-01", periods=3, freq="D")
    if horaria:
        janelas = exp.horario.JanelasHorarias(**metadados, origem_utc=datas.tz_localize("UTC"), origem_local=datas)
    else:
        alvos = datas.to_numpy()[:, None] + np.arange(2)[None, :] * np.timedelta64(1, "D")
        janelas = exp.base.JanelasDiretas(**metadados, origem=datas, datas_alvo=alvos)
    config = exp.base.ConfiguracaoMultirresolucao(timesnet_d_model=4, timesnet_d_ff=8,
                 timesnet_top_k=1, timesnet_kernels=1, threads_torch=1)
    escalas = pd.DataFrame({"localidade_id": [0, 1], "minimo_treino_wm2": [10., 100.],
                           "amplitude_escala_wm2": [10., 100.]})
    elevacoes = {"validacao_2023": np.tile([-2., 30.], (3, 1))} if horaria else {}
    return exp.dados.Contexto(tarefa, config, ["A", "B"], {"validacao_2023": janelas},
                              {"selecao": escalas}, elevacoes, [])


def _selecao_dupla(pasta, modo="completa"):
    """Pequena arvore de arquivos reais com hashes e os conjuntos de sementes."""
    for slug in exp.TAREFAS:
        tarefa = pasta / slug
        seeds = [42] if slug.startswith("hourly") else [11, 23, 42, 67, 89]
        if modo == "smoke":
            seeds = seeds[:1]
        contrato = {"tarefa": {"slug": slug}, "sementes": seeds, "modo": modo,
                    "codigo": {}, "entradas": {}, "fontes_configuracao": {},
                    "configuracao": {"max_epocas_diario": 30, "epocas_smoke": 1}}
        contrato["sha256_contrato"] = exp.hash_obj(contrato)
        _json(tarefa / "contrato_execucao.json", contrato)
        exp.base.salvar_csv_atomico(pd.DataFrame({"localidade_id": [0], "minimo_treino_wm2": [0.],
            "amplitude_escala_wm2": [100.]}), tarefa / "escalas_selecao.csv")
        ranking, hashes = [], {}
        for ordem, (nome, niveis) in enumerate(exp.VARIANTES):
            arquivo = tarefa / "variantes" / nome / "resultado_selecao.json"
            _json(arquivo, {"niveis": niveis, "sementes": seeds})
            hashes[str(arquivo.resolve())] = exp.base.sha256_arquivo(arquivo)
            ranking.append({"nome": nome, "niveis": niveis, "MAE_validacao_wm2": 10. + ordem,
                            "epocas": {str(seed): 1 if modo == "smoke" else 3 for seed in seeds}})
        _json(tarefa / "selecao_congelada.json", {"tarefa": slug, "modo": modo,
            "contrato_sha256": contrato["sha256_contrato"], "selecao_concluida_antes_do_teste": True,
            "ranking": ranking, "vencedor": ranking[0], "fontes_selecao_sha256": hashes})


@pytest.mark.parametrize("slug", exp.TAREFAS)
def test_refit_exige_congelamento_antes_de_ler_configuracao_ou_dados(tmp_path, monkeypatch, slug):
    def proibido(*args, **kwargs):
        pytest.fail("Configuracao/dados nao podem ser lidos antes do congelamento.")

    monkeypatch.setattr(exp, "parametros", proibido)
    monkeypatch.setattr(exp.base, "carregar_series_diarias", proibido)
    monkeypatch.setattr(exp.horario, "preparar_series_localidades", proibido)
    with pytest.raises(ValueError, match="Congele ambas"):
        exp.preparar_contexto(slug, "refit", tmp_path)


@pytest.mark.parametrize("modo", ["completa", "smoke"])
def test_congela_apenas_apos_duas_tarefas_quatro_variantes_e_suas_sementes(tmp_path, modo):
    _selecao_dupla(tmp_path, modo)
    resultado = exp.congelar_global(tmp_path)
    arquivo = tmp_path / "selecao_global_congelada.json"
    antes = arquivo.read_bytes()
    assert resultado["tarefas"] == list(exp.TAREFAS)
    assert len(resultado["fontes_selecao_sha256"]) == 14
    exp.validar_congelamento_global(tmp_path)
    assert exp.congelar_global(tmp_path) == resultado
    assert arquivo.read_bytes() == antes


@pytest.mark.parametrize("defeito", ["variante", "semente", "contrato", "incompleta", "artefato", "refit"])
def test_congelamento_rejeita_selecao_incompleta_ou_alterada(tmp_path, defeito):
    _selecao_dupla(tmp_path)
    pasta = tmp_path / "daily_30"
    arquivo = pasta / "selecao_congelada.json"
    selecao = exp.ler_json(arquivo)
    if defeito == "variante":
        selecao["ranking"].pop()
    elif defeito == "semente":
        selecao["ranking"][1]["epocas"].pop("89")
    elif defeito == "contrato":
        selecao["contrato_sha256"] = "outro"
    elif defeito == "incompleta":
        selecao["selecao_concluida_antes_do_teste"] = False
    elif defeito == "artefato":
        _json(Path(next(iter(selecao["fontes_selecao_sha256"]))), {"alterado": True})
    elif defeito == "refit":
        (pasta / "variantes" / "q64" / "refit").mkdir()
    _json(arquivo, selecao)
    with pytest.raises(ValueError):
        exp.congelar_global(tmp_path)
    assert not (tmp_path / "selecao_global_congelada.json").exists()


def test_congelamento_exige_arquivo_da_segunda_tarefa(tmp_path):
    _selecao_dupla(tmp_path)
    (tmp_path / "daily_30" / "selecao_congelada.json").unlink()
    with pytest.raises(FileNotFoundError):
        exp.congelar_global(tmp_path)


@pytest.mark.parametrize("defeito", ["hash", "duplicada", "nivel", "epoca_zero", "epoca_limite",
    "epoca_bool", "mae_nan", "mae_negativo", "vencedor", "ordem", "fonte_codigo", "tarefa", "modo"])
def test_selecao_valida_conteudo_contrato_ranking_e_vencedor(tmp_path, defeito):
    _selecao_dupla(tmp_path)
    pasta = tmp_path / "daily_30"
    caminho_c = pasta / "contrato_execucao.json"
    caminho_s = pasta / "selecao_congelada.json"
    c, s = exp.ler_json(caminho_c), exp.ler_json(caminho_s)
    if defeito == "hash":
        c["configuracao"]["max_epocas_diario"] = 40
    elif defeito == "duplicada":
        s["ranking"].append(s["ranking"][0].copy())
    elif defeito == "nivel":
        s["ranking"][1]["niveis"] = 128
    elif defeito in {"epoca_zero", "epoca_limite", "epoca_bool"}:
        s["ranking"][1]["epocas"]["11"] = {"epoca_zero": 0, "epoca_limite": 31, "epoca_bool": True}[defeito]
    elif defeito in {"mae_nan", "mae_negativo"}:
        s["ranking"][1]["MAE_validacao_wm2"] = float("nan") if defeito == "mae_nan" else -1.
    elif defeito == "vencedor":
        s["vencedor"] = s["ranking"][2]
    elif defeito == "ordem":
        s["ranking"] = list(reversed(s["ranking"]))
    elif defeito == "fonte_codigo":
        codigo = tmp_path / "codigo.json"
        _json(codigo, {"versao": 1})
        c["codigo"][str(codigo.resolve())] = exp.base.sha256_arquivo(codigo)
        c["sha256_contrato"] = exp.hash_obj({k: v for k, v in c.items() if k != "sha256_contrato"})
        s["contrato_sha256"] = c["sha256_contrato"]
        _json(codigo, {"versao": 2})
    elif defeito == "tarefa":
        s["tarefa"] = "monthly_1"
    else:
        s["modo"] = "smoke"
    _json(caminho_c, c)
    _json(caminho_s, s)
    with pytest.raises(ValueError):
        exp.validar_selecao(pasta)


def test_empate_preserva_ordem_predefinida_das_variantes(tmp_path):
    _selecao_dupla(tmp_path)
    pasta = tmp_path / "daily_30"
    caminho = pasta / "selecao_congelada.json"
    s = exp.ler_json(caminho)
    for r in s["ranking"]:
        r["MAE_validacao_wm2"] = 10.
    s["vencedor"] = s["ranking"][0]
    _json(caminho, s)
    _, validada = exp.validar_selecao(pasta)
    assert validada["vencedor"]["nome"] == "sem_quantizacao"


@pytest.mark.parametrize("defeito", ["selecao", "artefato", "lista_tarefas", "referencia"])
def test_apos_congelar_rejeita_alteracoes_das_fontes_e_referencias(tmp_path, defeito):
    _selecao_dupla(tmp_path)
    exp.congelar_global(tmp_path)
    arquivo = tmp_path / "selecao_global_congelada.json"
    global_ = exp.ler_json(arquivo)
    if defeito == "selecao":
        _json(tmp_path / "daily_30" / "selecao_congelada.json", {"alterado": True})
    elif defeito == "artefato":
        _json(tmp_path / "hourly_72_extension" / "variantes" / "q64" / "resultado_selecao.json", {})
    elif defeito == "lista_tarefas":
        global_["tarefas"].pop()
    else:
        global_["fontes_selecao_sha256"].pop(str((tmp_path / "daily_30" / "selecao_congelada.json").resolve()))
    _json(arquivo, global_)
    with pytest.raises(ValueError):
        exp.validar_congelamento_global(tmp_path)


def _cache(tmp_path, niveis=64, contrato="contrato"):
    variante = tmp_path / "q64"
    cache = variante / "selecao" / "seed11.npz"
    exp.base.salvar_npz_atomico(cache, previsao=np.array([[1.25, -2.]]), epocas=np.asarray(3))
    hist = cache.with_suffix(".csv")
    exp.base.salvar_csv_atomico(pd.DataFrame({"epoca": [1, 2, 3]}), hist)
    cp = variante / "modelos" / "timesnet_seed11_selecao.pt"
    exp.base.salvar_torch_atomico({"semente": 11}, cp)
    meta = {"contrato_sha256": contrato, "niveis": niveis, "semente": 11, "epocas": 3,
            "fase": "selecao", "variante": "q64", "epocas_fixas": None,
            "arquivos_sha256": {str(p.resolve()): exp.base.sha256_arquivo(p) for p in (cache, hist, cp)}}
    _json(cache.with_suffix(".json"), meta)
    return variante, cache, meta


def _ler_cache(variante):
    avaliacao = SimpleNamespace(localidade_id=np.array([0]), pred_len=2)
    return exp._seed_job(str(variante), None, None, None, 11, None, avaliacao, None, None,
                         "q64", 64, "contrato", "selecao", "cpu")


def test_cache_valido_retorna_resultado_sem_retreinar(tmp_path, monkeypatch):
    variante, _, _ = _cache(tmp_path)
    monkeypatch.setattr(exp.treino, "treinar", lambda **kw: pytest.fail("Cache valido nao deve retreinar."))
    resultado = _ler_cache(variante)
    assert resultado["semente"] == 11 and resultado["epocas"] == 3
    np.testing.assert_array_equal(resultado["previsao"], [[1.25, -2.]])


@pytest.mark.parametrize("defeito", ["contrato", "niveis", "previsao", "checkpoint", "historico",
                                   "semente", "fase", "variante", "epocas_fixas", "epocas"])
def test_cache_rejeita_mudanca_de_contrato_niveis_e_artefatos(tmp_path, defeito):
    variante, cache, meta = _cache(tmp_path)
    if defeito == "contrato":
        meta["contrato_sha256"] = "alterado"
    elif defeito == "niveis":
        meta["niveis"] = 128
    elif defeito == "previsao":
        exp.base.salvar_npz_atomico(cache, previsao=np.zeros((1, 2)), epocas=np.asarray(3))
    elif defeito == "checkpoint":
        exp.base.salvar_torch_atomico({"semente": 23}, variante / "modelos" / "timesnet_seed11_selecao.pt")
    elif defeito == "historico":
        exp.base.salvar_csv_atomico(pd.DataFrame({"epoca": [4]}), cache.with_suffix(".csv"))
    else:
        meta[defeito] = {"semente": 23, "fase": "refit", "variante": "q256", "epocas_fixas": 3, "epocas": 4}[defeito]
    _json(cache.with_suffix(".json"), meta)
    with pytest.raises(ValueError):
        _ler_cache(variante)


@pytest.mark.parametrize("horaria", [False, True])
def test_salvar_avaliacao_faz_media_bruta_antes_piso_e_mascara_e_preserva_alvos(tmp_path, horaria):
    ctx = _contexto(horaria)
    janelas = ctx.janelas["validacao_2023"]
    verdade = janelas.y_bruto.copy()
    bruto1 = np.array([[-4., 4.], [8., -6.], [30., -4.]])
    bruto2 = np.array([[2., 6.], [0., 2.], [10., 6.]])
    media = (bruto1 + bruto2) / 2
    resultado = exp.salvar_avaliacao(ctx, tmp_path, [{"semente": 11, "previsao": bruto1},
        {"semente": 23, "previsao": bruto2}], "validacao_2023")
    tabela = pd.read_csv(tmp_path / "previsoes_validacao.csv.gz")
    pos = np.maximum(media, 0.)
    if horaria:
        pos[:, 0] = 0.
        np.testing.assert_array_equal(tabela.elevacao_solar_graus, ctx.elevacoes["validacao_2023"].reshape(-1))
    np.testing.assert_array_equal(tabela.previsao_bruta_timesnet_ensemble_wm2, media.reshape(-1))
    np.testing.assert_array_equal(tabela.previsao_pos_timesnet_ensemble_wm2, pos.reshape(-1))
    assert not np.array_equal(pos, (exp.dados.pos_processar(ctx, "validacao_2023", bruto1)
                                  + exp.dados.pos_processar(ctx, "validacao_2023", bruto2)) / 2)
    np.testing.assert_array_equal(tabela.ghi_real_wm2, verdade.reshape(-1))
    np.testing.assert_array_equal(janelas.y_bruto, verdade)
    maes = [np.abs(pos[janelas.localidade_id == i] - verdade[janelas.localidade_id == i]).mean() for i in (0, 1)]
    assert resultado == np.mean(maes)
    macro = pd.read_csv(tmp_path / "metricas_validacao_macro.csv")
    linha = macro[(macro.tipo_horizonte == "cumulativo") & (macro.horizonte == 2)]
    assert float(linha.MAE_wm2.iloc[0]) == resultado


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_diagnosticos_so_dependem_de_entradas_e_preservam_janelas(niveis):
    ctx = _contexto()
    janela = ctx.janelas["validacao_2023"]
    campos = {k: getattr(janela, k) for k in ("x_bruto", "localidade", "localidade_id", "seq_len", "pred_len")}
    sem_y = SimpleNamespace(**campos)
    original = janela.x_bruto.copy()
    esperado = exp.diagnosticos(janela, ctx.escalas["selecao"], niveis)
    assert exp.diagnosticos(sem_y, ctx.escalas["selecao"], niveis) == esperado
    assert esperado["total"]["total"] == janela.x_bruto.size
    assert esperado["total"]["total"] == sum(esperado[str(i)]["total"] for i in (0, 1))
    assert esperado["total"]["saturados"] == (0 if niveis is None else
        esperado["total"]["abaixo_zero"] + esperado["total"]["acima_um"])
    np.testing.assert_array_equal(janela.x_bruto, original)


@pytest.mark.parametrize("horaria", [False, True])
def test_contrato_assina_configuracao_codigo_dados_e_fontes(tmp_path, monkeypatch, horaria):
    ctx = _contexto(horaria)
    fonte = tmp_path / "fonte"
    monkeypatch.setattr(exp, "FONTE", fonte)
    for nome in ("contrato_execucao.json", "selecao_congelada.json", "manifesto_artefatos.json"):
        _json(fonte / ctx.tarefa.slug / nome, {"original": nome})
    entrada = tmp_path / "entrada.csv"
    exp.base.salvar_csv_atomico(pd.DataFrame({"ghi": [10.25, 20.33]}), entrada)
    ctx.entradas = [entrada]
    candidato = exp.origem.Candidato("fixo", 12)
    seeds = [42] if horaria else [11, 23, 42, 67, 89]
    c = exp.construir_contrato(ctx, candidato, seeds, "cpu", 1)
    assert c == exp.construir_contrato(ctx, candidato, seeds, "cpu", 1)
    sem_hash = {k: v for k, v in c.items() if k != "sha256_contrato"}
    assert c["sha256_contrato"] == exp.hash_obj(sem_hash)
    assert c["quantizacao"]["alvos_quantizados"] is False
    assert c["quantizacao"]["pesos_quantizados"] is False
    assert c["sementes"] == seeds
    for grupo in ("codigo", "entradas", "fontes_configuracao"):
        exp.conferir_hashes(c[grupo])
    ctx.config = replace(ctx.config, taxa_aprendizado=0.0003)
    assert exp.construir_contrato(ctx, candidato, seeds, "cpu", 1)["sha256_contrato"] != c["sha256_contrato"]
    exp.base.salvar_csv_atomico(pd.DataFrame({"ghi": [99.]}), entrada)
    with pytest.raises(ValueError, match="Fonte alterada"):
        exp.conferir_hashes(c["entradas"])


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_checkpoint_reconstroi_preprocessamento_sem_ler_alvos(tmp_path, niveis):
    ctx = _contexto()
    janela = ctx.janelas["validacao_2023"]
    exp.base.fixar_semente(11, 1)
    modelo = exp.base.criar_modelo_neural("TimesNet", tarefa=ctx.tarefa, configuracao=ctx.config,
                                         num_localidades=2, semente=11)
    cp = {"tarefa": asdict(ctx.tarefa), "configuracao": asdict(ctx.config), "semente": 11,
          "state_dict": modelo.state_dict(), "preprocessamento": {"versao": 1, "minmax": True,
              "onde": "somente_entradas", "niveis": niveis, "escalas": ctx.escalas["selecao"].to_dict("records"),
              "dispositivo": "cpu", "batch_size": 2, "localidades": {"0": "A", "1": "B"}}}
    arquivo = tmp_path / "checkpoint.pt"
    exp.base.salvar_torch_atomico(cp, arquivo)
    campos = {k: getattr(janela, k) for k in ("x_bruto", "localidade", "localidade_id", "seq_len", "pred_len")}
    sem_y = SimpleNamespace(**campos)
    previsto = exp.prever_checkpoint(arquivo, sem_y)
    esperado = exp.treino.prever(modelo, janela, ctx.escalas["selecao"], 2, niveis=niveis)
    np.testing.assert_array_equal(previsto, esperado)
    sem_y.localidade = np.array(["ERRADO", "A", "B"])
    with pytest.raises(ValueError, match="Identidade"):
        exp.prever_checkpoint(arquivo, sem_y)


def test_execucao_protege_fonte_e_libera_lock_apos_erro(tmp_path, monkeypatch):
    fonte = tmp_path / "historico"
    monkeypatch.setattr(exp, "FONTE", fonte)
    with pytest.raises(ValueError, match="resultados fonte"):
        exp.executar("daily_30", pasta_saida=fonte)
    with pytest.raises(ValueError, match="resultados fonte"):
        exp.executar("daily_30", pasta_saida=fonte / "filho")
    def falhar(*args, **kwargs):
        raise ValueError("erro controlado")
    monkeypatch.setattr(exp, "preparar_contexto", falhar)
    nova = tmp_path / "nova"
    with pytest.raises(ValueError, match="erro controlado"):
        exp.executar("daily_30", pasta_saida=nova)
    assert not (nova / ".daily_30.lock").exists()
