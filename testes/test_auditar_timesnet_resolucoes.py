"""Auditoria independente: hashes, alinhamento e agregacao das metricas."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from codigo_fonte import otimizacao_timesnet_resolucoes as busca

from scripts import auditar_timesnet_resolucoes as audit
from testes.test_otimizacao_timesnet_resolucoes import _contexto, _busca_falsa, _Rede


def test_manifesto_detecta_arquivo_alterado_e_nao_escreve_nas_fontes(tmp_path):
    arquivo = tmp_path / "resultado.txt"
    arquivo.write_text("123", encoding="utf-8")
    manifesto = audit.m.gerar_manifesto_artefatos(tmp_path)
    (tmp_path / "manifesto_artefatos.json").write_text(json.dumps(manifesto), encoding="utf-8")
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert audit.conferir_manifesto(tmp_path)["arquivos_verificados"] == 1
    assert antes == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    arquivo.write_text("124", encoding="utf-8")
    with pytest.raises(ValueError, match="alterado"):
        audit.conferir_manifesto(tmp_path)


def test_manifesto_recusa_arquivo_omitido(tmp_path):
    (tmp_path / "manifesto_artefatos.json").write_text(json.dumps({"N_arquivos": 0, "arquivos": []}))
    (tmp_path / "extra.txt").write_text("novo")
    with pytest.raises(ValueError, match="Inventario"):
        audit.conferir_manifesto(tmp_path)


def test_contrato_detecta_hash_interno_e_hash_da_fonte(tmp_path):
    fonte = tmp_path / "fonte.txt"
    fonte.write_text("dados")
    contrato = {"codigo": {}, "entradas": {str(fonte): audit.m.sha256_arquivo(fonte)}}
    contrato["sha256_contrato"] = hashlib.sha256(json.dumps(contrato, sort_keys=True).encode()).hexdigest()
    assert audit.conferir_contrato(contrato) == {"codigo": 0, "entradas": 1}
    contrato["extra"] = "mudou"
    with pytest.raises(ValueError, match="interno"):
        audit.conferir_contrato(contrato)
    contrato.pop("extra")
    fonte.write_text("outros")
    with pytest.raises(ValueError, match="alterado"):
        audit.conferir_contrato(contrato)


@pytest.mark.parametrize("horario", [False, True])
def test_alinhamento_reordena_datas_e_preserva_canonico(horario):
    ctx = _contexto(horario)
    tabela = audit.e.tabela_chaves(ctx, "teste_2024")
    tabela[audit.BRUTA] = tabela.ghi_real_wm2 + 10
    tabela[audit.POS] = tabela[audit.BRUTA]
    esperado = tabela[audit.BRUTA].to_numpy()
    resultado = audit.alinhar_tabela(ctx, "teste_2024", tabela.iloc[::-1])
    np.testing.assert_array_equal(resultado[audit.BRUTA], esperado)
    tabela.loc[0, "ghi_real_wm2"] += 1
    with pytest.raises(ValueError, match="Alvos canonicos"):
        audit.alinhar_tabela(ctx, "teste_2024", tabela)


def test_metricas_macro_sao_media_das_metricas_locais():
    tabela = pd.DataFrame({"localidade": ["A", "A", "B", "B"], "passo": [1, 2, 1, 2],
                          "ghi_real_wm2": [1., 3., 10., 30.], audit.POS: [2., 4., 13., 33.]})
    locais, macro = audit.metricas_independentes(tabela, [1, 2])
    cumulativo = macro.loc[(macro.tipo_horizonte == "cumulativo") & (macro.horizonte == 2)].iloc[0]
    assert cumulativo.MAE_wm2 == pytest.approx(2.)
    assert cumulativo.MSE_w2m4 == pytest.approx(5.)
    assert cumulativo.RMSE_wm2 == pytest.approx(2.)
    assert cumulativo.nRMSE == pytest.approx(.325)
    assert cumulativo.R2 == pytest.approx(.455)
    assert audit.comparar_metricas(locais, locais.iloc[::-1], True) == 0
    assert audit.comparar_metricas(macro, macro.iloc[::-1]) == 0
    adulterado = macro.copy()
    adulterado.loc[0, "MAE_wm2"] += 1
    with pytest.raises(ValueError, match="Metricas macro"):
        audit.comparar_metricas(macro, adulterado)


def test_epoca_escolhida_respeita_primeiro_minimo_e_tolerancia():
    historico = pd.DataFrame({"epoca": [1, 2, 3, 4], "mae_validacao_wm2": [10., 8., 8. - 1e-13, 9.]})
    assert audit.epoca_historico(historico) == 2
    historico.loc[2, "epoca"] = 9
    with pytest.raises(ValueError, match="consecutivas"):
        audit.epoca_historico(historico)


def test_evidencia_mensal_nao_considera_inferencia_antiga_como_nova(monkeypatch, tmp_path):
    tarefas = []
    for slug in ("monthly_1", "monthly_6"):
        pasta = tmp_path / slug
        pasta.mkdir()
        contrato = pasta / "contrato_execucao.json"
        contrato.write_text(json.dumps({"entradas": []}), encoding="utf-8")
        (pasta / "manifesto_artefatos.json").write_text(json.dumps(audit.m.gerar_manifesto_artefatos(pasta)), encoding="utf-8")
        tarefas.append({"tarefa": slug, "fontes": {"contrato_execucao.json": audit.m.sha256_arquivo(contrato)},
                        "checkpoints": [{"erro_maximo_npz_wm2": 0.} for _ in range(5)],
                        "comparacao": {"teste_timesnet": 13.}, "codigo": {"orquestrador.py": {"confere_atualmente": False}},
                        "limitacoes": ["teste ja observado"]})
    relatorio = tmp_path / "auditoria_anterior.json"
    relatorio.write_text(json.dumps({"fonte": str(tmp_path), "gerado_em_utc": "2026-09-22", "tarefas": tarefas}), encoding="utf-8")
    resultado = audit.evidencia_mensal(relatorio)
    assert resultado["reproducao_mensal_nao_reexecutada_nesta_auditoria"] is True
    assert resultado["valores_sustentados_pelos_artefatos_preservados"] is True
    assert resultado["tarefas"][0]["codigo_divergente_declarado"] == ["orquestrador.py"]


@pytest.mark.parametrize("reproduzir", [False, True])
def test_auditoria_completa_com_inferencia_simulada_e_corrupcao_de_metrica(monkeypatch, tmp_path, reproduzir):
    ctx, saida, registros, _ = _busca_falsa(monkeypatch, tmp_path)
    treinamento = busca.treino.treinar

    def treinar_com_historico(**kwargs):
        modelo, n, hist = treinamento(**kwargs)
        valor = hist.mae_validacao_wm2.iloc[0]
        historico = pd.DataFrame({"epoca": np.arange(1, n + 1),
            "mae_validacao_wm2": [valor + n - i for i in range(1, n + 1)]})
        return modelo, n, historico

    def contrato(contexto, candidatos, dispositivo):
        c = {"tarefa": asdict(contexto.tarefa), "configuracao": asdict(contexto.config),
             "candidatos": [asdict(x) for x in candidatos], "dispositivo": dispositivo,
             "codigo": {str(Path(__file__).resolve()): audit.m.sha256_arquivo(__file__)},
             "entradas": {}, "sementes": [11, 23], "criterio": "MAE_validacao", "limitacoes": []}
        c["sha256_contrato"] = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
        return c

    monkeypatch.setattr(busca.treino, "treinar", treinar_com_historico)
    monkeypatch.setattr(busca, "contrato", contrato)
    busca.executar(ctx.tarefa.slug, saida)
    monkeypatch.setattr(audit.e, "preparar_contexto", lambda *args: ctx)
    monkeypatch.setattr(audit.e, "verificar_alinhamento", lambda *args: None)
    monkeypatch.setattr(audit.m, "criar_modelo_neural", lambda *args, **kwargs: _Rede(50.))
    pasta = saida / ctx.tarefa.slug
    resultado = audit.auditar_tarefa(pasta, reproduzir)
    assert resultado["ok"] is True
    assert resultado["particoes"]["teste_2024"]["MAE_wm2"] == pytest.approx(50.)
    assert all(c["reproduzido"] is reproduzir for c in resultado["checkpoints"]["modelos"])
    if reproduzir:
        assert all(c["erro_maximo_reproducao_wm2"] == 0 for c in resultado["checkpoints"]["modelos"])
    # A verificacao numerica deve detectar erro mesmo se alguem recriar o manifesto.
    arquivo = pasta / "metricas_teste_macro.csv"
    metricas = pd.read_csv(arquivo)
    metricas.loc[0, "MAE_wm2"] += 10
    metricas.to_csv(arquivo, index=False)
    (pasta / "manifesto_artefatos.json").write_text(json.dumps(audit.m.gerar_manifesto_artefatos(pasta)), encoding="utf-8")
    with pytest.raises(ValueError, match="Metricas macro"):
        audit.auditar_tarefa(pasta)
