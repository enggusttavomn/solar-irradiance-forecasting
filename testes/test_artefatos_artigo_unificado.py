from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import codigo_fonte.artefatos_artigo_unificado as artefatos
from codigo_fonte.artefatos_fragmentados import preparar_manifesto_fragmentado
from codigo_fonte.artefatos_artigo_unificado import (
    ArtefatoNaoPublicavelError,
    gerar_artefatos_artigo_unificado,
    sha256_arquivo,
)


SEMENTES = (11, 23, 42, 67, 89)
LOCAIS = ("Factory & North", "Factory South")


def test_latex_contem_tabular_na_largura_da_coluna_e_fecha_balanceado(
    tmp_path: Path,
) -> None:
    caminho = tmp_path / "tabela.tex"
    quadro = pd.DataFrame([{f"coluna_{i}": i for i in range(11)}])

    artefatos._gravar_latex(
        quadro,
        caminho,
        legenda="Tabela larga & auditavel",
        rotulo="tab:tabela_larga",
    )

    latex = caminho.read_text(encoding="utf-8")
    assert latex.count(r"\resizebox{\linewidth}{!}{%") == 1
    assert latex.count(r"\begin{tabular}") == 1
    assert latex.count(r"\end{tabular}") == 1
    assert latex.count(r"\begin{table}") == 1
    assert latex.count(r"\end{table}") == 1
    assert r"\toprule" in latex
    assert r"\midrule" in latex
    assert r"\bottomrule" in latex
    assert "\\end{tabular}%\n}\n\\end{table}" in latex
    assert latex.index(r"\resizebox{\linewidth}{!}{%") < latex.index(
        r"\begin{tabular}"
    )


def test_caminho_portatil_remove_prefixo_da_maquina() -> None:
    caminho = artefatos.RAIZ_PROJETO / "codigo_fonte" / "artefatos_artigo_unificado.py"

    assert artefatos.caminho_portatil(caminho) == (
        "codigo_fonte/artefatos_artigo_unificado.py"
    )


def test_json_auditavel_permanece_lf_em_todas_as_plataformas() -> None:
    atributos = (Path(__file__).resolve().parents[1] / ".gitattributes").read_text(
        encoding="utf-8"
    )

    assert "*.json text eol=lf" in atributos.splitlines()


def test_promocao_atomica_repete_winerrors_transitorios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temporaria = tmp_path / "temporaria"
    destino = tmp_path / "destino"
    temporaria.mkdir()
    (temporaria / "completo.txt").write_text("completo", encoding="utf-8")
    substituir_real = artefatos.os.replace
    codigos = [5, 32, 33]
    chamadas: list[int] = []
    atrasos: list[float] = []

    def substituir_instavel(origem: Path, alvo: Path) -> None:
        chamadas.append(1)
        if len(chamadas) <= len(codigos):
            erro = PermissionError("bloqueio transitorio simulado")
            erro.winerror = codigos[len(chamadas) - 1]
            raise erro
        substituir_real(origem, alvo)

    monkeypatch.setattr(artefatos.os, "replace", substituir_instavel)
    monkeypatch.setattr(artefatos.time, "sleep", atrasos.append)

    artefatos._promover_pasta_com_retry(temporaria, destino)

    assert len(chamadas) == 4
    assert atrasos == list(artefatos._ATRASOS_PROMOCAO_WINDOWS_S[:3])
    assert not temporaria.exists()
    assert (destino / "completo.txt").read_text(encoding="utf-8") == "completo"


def test_promocao_atomica_nao_sobrescreve_destino_existente(tmp_path: Path) -> None:
    temporaria = tmp_path / "temporaria"
    destino = tmp_path / "destino"
    temporaria.mkdir()
    destino.mkdir()
    (temporaria / "novo.txt").write_text("novo", encoding="utf-8")
    (destino / "existente.txt").write_text("preservar", encoding="utf-8")

    with pytest.raises(FileExistsError, match="nao sera sobrescrita"):
        artefatos._promover_pasta_com_retry(temporaria, destino)

    assert (temporaria / "novo.txt").is_file()
    assert (destino / "existente.txt").read_text(encoding="utf-8") == "preservar"


def _json(caminho: Path, valor: object) -> None:
    caminho.write_text(
        json.dumps(valor, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _contrato(tarefa: str) -> dict[str, object]:
    base: dict[str, object] = {
        "versao_contrato": 1,
        "tarefa": {"slug": tarefa},
        "configuracao": {"modo_execucao": "completa"},
        "entradas_sha256": {},
        "codigo_sha256": {},
    }
    serializado = json.dumps(
        base, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    base["sha256_contrato"] = hashlib.sha256(serializado).hexdigest()
    return base


def _linha_metrica(
    *,
    tarefa: str,
    resolucao: str,
    modelo: str,
    tipo: str,
    semente: int | None,
    mae: float,
    localidade: str | None = None,
    horizonte: int = 1,
) -> dict[str, object]:
    linha: dict[str, object] = {
        "tarefa": tarefa,
        "resolucao": resolucao,
        "particao": "teste_2024",
        "modelo": modelo,
        "tipo_estimativa": tipo,
        "semente": semente,
        "tipo_horizonte": "cumulativo",
        "horizonte": horizonte,
        "N_origens": 2,
        "N_pontos": 4,
        "MAE_wm2": mae,
        "RMSE_wm2": mae + 2.0,
        "nRMSE": (mae + 2.0) / 100.0,
        "R2": 0.9 - mae / 1000.0,
    }
    if localidade is None:
        linha.update(
            {
                "N_localidades": 2,
                "agregacao": "media_aritmetica_das_metricas_por_localidade",
            }
        )
    else:
        linha["localidade"] = localidade
    return linha


def _manifestar_tarefa(pasta: Path) -> None:
    arquivos = []
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file() or caminho.name == "manifesto_artefatos.json":
            continue
        arquivos.append(
            {
                "arquivo": caminho.relative_to(pasta).as_posix(),
                "bytes": caminho.stat().st_size,
                "sha256": sha256_arquivo(caminho),
            }
        )
    _json(
        pasta / "manifesto_artefatos.json",
        {
            "gerado_em_utc": "2026-01-01T00:00:00+00:00",
            "N_arquivos": len(arquivos),
            "arquivos": arquivos,
        },
    )


def _artefatos_comuns(
    pasta: Path,
    *,
    tarefa: str,
    resolucao: str,
    macro: pd.DataFrame,
    locais: pd.DataFrame,
    epocas: pd.DataFrame,
    status: dict[str, object],
    hiperparametros: dict[str, object],
) -> None:
    pasta.mkdir(parents=True)
    contrato = _contrato(tarefa)
    status["sha256_contrato"] = contrato["sha256_contrato"]
    _json(pasta / "contrato_execucao.json", contrato)
    _json(pasta / "status_execucao.json", status)
    macro.to_csv(pasta / "metricas_macro.csv", index=False)
    locais.to_csv(pasta / "metricas_por_localidade.csv", index=False)
    epocas.to_csv(pasta / "epocas_selecionadas.csv", index=False)
    pd.DataFrame(
        [{"tarefa": tarefa, "fase": "refit", "modelo": "TimesNet", "epoca": 1, "MSE": 0.1}]
    ).to_csv(pasta / "historico_treinamento.csv", index=False)
    pd.DataFrame(
        [{"tarefa": tarefa, "resolucao": resolucao, "localidade": LOCAIS[0]}]
    ).to_csv(pasta / "protocolo_temporal.csv", index=False)
    pd.DataFrame(
        [{"tarefa": tarefa, "fase": "refit", "minimo": 0.0, "maximo": 1000.0}]
    ).to_csv(pasta / "escalas_minmax_pre_corte.csv", index=False)
    pd.DataFrame(
        [
            {
                "tarefa": tarefa,
                "resolucao": resolucao,
                "tipo_horizonte": "cumulativo",
                "horizonte": 1,
                "localidade": LOCAIS[0],
                "metrica": "MAE_wm2",
                "valor_timesnet": 8.0,
                "valor_dilatedrnn": 10.0,
                "diferenca_timesnet_menos_dilatedrnn": -2.0,
                "melhor_timesnet": True,
                "unidade_pareamento": "localidade",
            }
        ]
    ).to_csv(pasta / "comparacao_pareada_localidades.csv", index=False)
    pd.DataFrame(
        [
            {
                "tarefa": tarefa,
                "resolucao": resolucao,
                "tipo_horizonte": "cumulativo",
                "horizonte": 1,
                "metrica": "MAE_wm2",
                "N_localidades": 2,
                "vitorias_timesnet": 1,
            }
        ]
    ).to_csv(pasta / "comparacao_pareada_resumo.csv", index=False)
    _json(pasta / "hiperparametros_e_metodo.json", hiperparametros)


def _criar_tarefa_diaria(raiz: Path) -> Path:
    pasta = raiz / "daily_30"
    macro: list[dict[str, object]] = []
    locais: list[dict[str, object]] = []
    maes_locais = {
        ("TimesNet", LOCAIS[0]): 8.0,
        ("DilatedRNN", LOCAIS[0]): 10.0,
        ("TimesNet", LOCAIS[1]): 12.0,
        ("DilatedRNN", LOCAIS[1]): 9.0,
    }
    for modelo, mae_ensemble in (("TimesNet", 10.0), ("DilatedRNN", 9.5)):
        for indice, semente in enumerate(SEMENTES):
            macro.append(
                _linha_metrica(
                    tarefa="daily_30",
                    resolucao="diaria",
                    modelo=modelo,
                    tipo="semente",
                    semente=semente,
                    mae=mae_ensemble + (indice - 2) * 0.1,
                )
            )
            for local in LOCAIS:
                locais.append(
                    _linha_metrica(
                        tarefa="daily_30",
                        resolucao="diaria",
                        modelo=modelo,
                        tipo="semente",
                        semente=semente,
                        mae=maes_locais[(modelo, local)] + (indice - 2) * 0.1,
                        localidade=local,
                    )
                )
        macro.append(
            _linha_metrica(
                tarefa="daily_30",
                resolucao="diaria",
                modelo=modelo,
                tipo="ensemble",
                semente=None,
                mae=mae_ensemble,
            )
        )
        for local in LOCAIS:
            locais.append(
                _linha_metrica(
                    tarefa="daily_30",
                    resolucao="diaria",
                    modelo=modelo,
                    tipo="ensemble",
                    semente=None,
                    mae=maes_locais[(modelo, local)],
                    localidade=local,
                )
            )
    macro.append(
        _linha_metrica(
            tarefa="daily_30",
            resolucao="diaria",
            modelo="Persistencia",
            tipo="deterministica",
            semente=None,
            mae=14.0,
        )
    )
    for local in LOCAIS:
        locais.append(
            _linha_metrica(
                tarefa="daily_30",
                resolucao="diaria",
                modelo="Persistencia",
                tipo="deterministica",
                semente=None,
                mae=14.0,
                localidade=local,
            )
        )
    epocas = pd.DataFrame(
        [
            {
                "tarefa": "daily_30",
                "modelo": modelo,
                "semente": seed,
                "epocas_selecionadas_em_2023": 8 + indice,
            }
            for modelo in ("TimesNet", "DilatedRNN")
            for indice, seed in enumerate(SEMENTES)
        ]
    )
    status: dict[str, object] = {
        "tarefa": "daily_30",
        "etapa": "concluida",
        "modo_execucao": "completa",
        "resultado_publicavel": True,
        "resultado_smoke_nao_publicavel": False,
        "carater_exploratorio": False,
        "N_localidades": 2,
        "sementes_efetivas": list(SEMENTES),
    }
    _artefatos_comuns(
        pasta,
        tarefa="daily_30",
        resolucao="diaria",
        macro=pd.DataFrame(macro),
        locais=pd.DataFrame(locais),
        epocas=epocas,
        status=status,
        hiperparametros={
            "configuracao": {
                "timesnet_d_model": 8,
                "dilated_dilatacoes": [1, 2, 4],
                "batch_size_diario": 128,
                "taxa_aprendizado": 0.001,
            }
        },
    )
    previsoes = pd.DataFrame(
        [
            {
                "tarefa": "daily_30",
                "particao": "teste_2024",
                "localidade": LOCAIS[0],
                "localidade_id": 0,
                "origem": "2024-01-01",
                "data_alvo": "2024-01-02",
                "passo": 1,
                "ghi_real_wm2": 100.0,
                "previsao_pos_timesnet_ensemble_wm2": 130.0,
                "previsao_pos_dilatedrnn_ensemble_wm2": 105.0,
            },
            {
                "tarefa": "daily_30",
                "particao": "teste_2024",
                "localidade": LOCAIS[0],
                "localidade_id": 0,
                "origem": "2024-01-02",
                "data_alvo": "2024-01-03",
                "passo": 1,
                "ghi_real_wm2": 100.0,
                "previsao_pos_timesnet_ensemble_wm2": 95.0,
                "previsao_pos_dilatedrnn_ensemble_wm2": 80.0,
            },
            {
                "tarefa": "daily_30",
                "particao": "teste_2024",
                "localidade": LOCAIS[1],
                "localidade_id": 1,
                "origem": "2024-01-01",
                "data_alvo": "2024-01-02",
                "passo": 1,
                "ghi_real_wm2": 100.0,
                "previsao_pos_timesnet_ensemble_wm2": 95.0,
                "previsao_pos_dilatedrnn_ensemble_wm2": 90.0,
            },
            {
                "tarefa": "daily_30",
                "particao": "teste_2024",
                "localidade": LOCAIS[1],
                "localidade_id": 1,
                "origem": "2024-01-02",
                "data_alvo": "2024-01-03",
                "passo": 1,
                "ghi_real_wm2": 100.0,
                "previsao_pos_timesnet_ensemble_wm2": 98.0,
                "previsao_pos_dilatedrnn_ensemble_wm2": 96.0,
            },
        ]
    )
    previsoes.to_csv(pasta / "previsoes_teste.csv.gz", index=False, compression="gzip")
    previsoes.iloc[:2].assign(particao="validacao_2023").to_csv(
        pasta / "previsoes_validacao.csv.gz", index=False, compression="gzip"
    )
    pd.DataFrame(
        [{"localidade": local, "arquivo": f"{local}.csv"} for local in LOCAIS]
    ).to_csv(pasta / "auditoria_entradas.csv", index=False)
    pd.DataFrame(
        [
            {
                "tarefa": "daily_30",
                "resolucao": "diaria",
                "particao": "teste_2024",
                "modelo": modelo,
                "tipo_horizonte": "cumulativo",
                "horizonte": 1,
                "N_sementes": 5,
                "MAE_wm2_media": 10.0,
            }
            for modelo in ("TimesNet", "DilatedRNN")
        ]
    ).to_csv(pasta / "variabilidade_sementes.csv", index=False)
    _manifestar_tarefa(pasta)
    return pasta


def _criar_tarefa_horaria(raiz: Path) -> Path:
    pasta = raiz / "hourly_72_extension"
    macro = pd.DataFrame(
        [
            _linha_metrica(
                tarefa="hourly_72_extension",
                resolucao="horaria",
                modelo=modelo,
                tipo="semente",
                semente=42,
                mae=mae,
                horizonte=24,
            )
            for modelo, mae in (("TimesNet", 11.0), ("DilatedRNN", 12.0))
        ]
    )
    locais = pd.DataFrame(
        [
            _linha_metrica(
                tarefa="hourly_72_extension",
                resolucao="horaria",
                modelo=modelo,
                tipo="semente",
                semente=42,
                mae=mae + indice,
                localidade=local,
                horizonte=24,
            )
            for modelo, mae in (("TimesNet", 11.0), ("DilatedRNN", 12.0))
            for indice, local in enumerate(LOCAIS)
        ]
    )
    status: dict[str, object] = {
        "tarefa": "hourly_72_extension",
        "etapa": "concluida",
        "modo_execucao": "completa",
        "resultado_publicavel": True,
        "resultado_smoke_nao_publicavel": False,
        "modelo_adicionado": "DilatedRNN",
        "semente": 42,
        "N_localidades": 2,
    }
    _artefatos_comuns(
        pasta,
        tarefa="hourly_72_extension",
        resolucao="horaria",
        macro=macro,
        locais=locais,
        epocas=pd.DataFrame(
            [
                {
                    "tarefa": "hourly_72_extension",
                    "modelo": "DilatedRNN",
                    "semente": 42,
                    "epocas_selecionadas_em_2023": 7,
                }
            ]
        ),
        status=status,
        hiperparametros={
            "dilatacoes": [1, 2, 4],
            "unidades_por_camada": 16,
            "batch_size": 128,
            "max_epocas": 30,
            "taxa_aprendizado": 0.001,
        },
    )
    previsoes = pd.DataFrame(
        [
            {
                "particao": "teste_2024",
                "semente": 42,
                "localidade": local,
                "localidade_id": indice,
                "origem_utc": f"2024-01-0{dia - 1} 00:00:00+00:00",
                "origem_local_fixa": f"2024-01-0{dia - 1} 21:00:00",
                "timestamp_alvo_utc": f"2024-01-0{dia} 15:00:00+00:00",
                "timestamp_alvo_local_fixo": f"2024-01-0{dia} 12:00:00",
                "passo_h": passo,
                "ghi_real_wm2": 100.0,
                "elevacao_solar_graus": 50.0,
                "periodo_diurno": True,
                "previsao_pos_timesnet_wm2": timesnet,
                "previsao_pos_dilatedrnn_wm2": dilated,
            }
            for indice, local in enumerate(LOCAIS)
            for dia, passo, timesnet, dilated in (
                (2, 1, 95.0, 80.0),
                (3, 1, 130.0, 105.0),
            )
        ]
    )
    previsoes.to_csv(pasta / "previsoes_teste.csv.gz", index=False, compression="gzip")
    previsoes.iloc[:2].assign(particao="validacao_2023").to_csv(
        pasta / "previsoes_validacao.csv.gz", index=False, compression="gzip"
    )
    _json(
        pasta / "vinculo_artefatos_oficiais.json",
        {"politica": "somente_DilatedRNN_seed42", "sha256_manifesto_oficial": "0" * 64},
    )
    _manifestar_tarefa(pasta)
    return pasta


def _criar_contexto(raiz: Path) -> tuple[Path, Path]:
    csv = raiz / "contexto.csv"
    manifesto = raiz / "contexto_manifesto.json"
    linhas = []
    for local in LOCAIS:
        for dia, precipitacao, nuvens in ((2, 2.0, 50.0), (3, 0.0, 10.0)):
            chuva = precipitacao >= 1.0
            nublado = nuvens >= 80.0
            linhas.append(
                {
                    "data_local": f"2024-01-0{dia}",
                    "localidade": local,
                    "latitude_fabrica": 0.0,
                    "longitude_fabrica": 0.0,
                    "precipitacao_corrigida_mm_dia": precipitacao,
                    "nebulosidade_percentual": nuvens,
                    "irradiacao_all_sky_kwh_m2_dia": 3.0,
                    "irradiacao_clear_sky_kwh_m2_dia": 5.0,
                    "indice_all_sky_clear_sky": 0.6,
                    "chuva_relevante": chuva,
                    "muito_nublado": nublado,
                    "condicao_adversa_independente": chuva or nublado,
                    "fonte_contexto": "NASA POWER Daily API",
                    "time_standard": "LST",
                }
            )
    pd.DataFrame(linhas).to_csv(csv, index=False)
    _json(
        manifesto,
        {
            "consultas": [],
            "criterios_predeclarados": {
                "adverso": "chuva_relevante OU muito_nublado",
                "chuva_relevante_mm_dia": 1.0,
                "muito_nublado_percentual": 80.0,
            },
            "linhas": len(linhas),
            "parametros": [
                "PRECTOTCORR",
                "CLOUD_AMT",
                "ALLSKY_SFC_SW_DWN",
                "CLRSKY_SFC_SW_DWN",
            ],
            "sha256_csv": sha256_arquivo(csv),
            "uso": "contexto pos-hoc da analise de erros",
            "uso_no_modelo": False,
        },
    )
    return csv, manifesto


def test_materializa_previsoes_fragmentadas_sem_alterar_bytes(tmp_path: Path) -> None:
    tarefa = _criar_tarefa_diaria(tmp_path / "entradas")
    nomes = ("previsoes_validacao.csv.gz", "previsoes_teste.csv.gz")
    originais = {nome: (tarefa / nome).read_bytes() for nome in nomes}

    manifesto = preparar_manifesto_fragmentado(
        tarefa,
        nomes,
        tamanho_parte=257,
    )
    assert {item["arquivo"] for item in manifesto["arquivos_fragmentados"]} == set(
        nomes
    )
    for nome in nomes:
        (tarefa / nome).unlink()

    artefatos.validar_pasta_tarefa(tarefa)

    assert {nome: (tarefa / nome).read_bytes() for nome in nomes} == originais


def test_gera_pacote_auditavel_e_casos_por_contexto_independente(tmp_path: Path) -> None:
    tarefa = _criar_tarefa_diaria(tmp_path / "entradas")
    contexto, manifesto_contexto = _criar_contexto(tmp_path)
    saida = tmp_path / "saida"

    resumo = gerar_artefatos_artigo_unificado(
        pastas_tarefas=[tarefa],
        caminho_contexto_nasa=contexto,
        caminho_manifesto_contexto_nasa=manifesto_contexto,
        pasta_saida=saida,
        chunksize=2,
    )

    assert resumo["tarefas"] == ["daily_30"]
    esperados = {
        "desempenho_macro.csv",
        "desempenho_macro.tex",
        "comparacao_timesnet_dilatedrnn_resumo.csv",
        "comparacao_timesnet_dilatedrnn_resumo.tex",
        "contrastes_por_origem_horizonte.csv",
        "caso_maior_ganho_timesnet.csv",
        "caso_maior_ganho_timesnet.tex",
        "caso_maior_deficit_timesnet.csv",
        "caso_maior_deficit_timesnet.tex",
        "caso_meteorologico_independente.csv",
        "caso_meteorologico_independente.tex",
        "ranking_por_tarefa.png",
        "ranking_por_tarefa.pdf",
        "previsoes_casos_contrastantes.png",
        "previsoes_casos_contrastantes.pdf",
        "variabilidade_por_semente.png",
        "variabilidade_por_semente.pdf",
        "configuracao_treinamento.csv",
        "configuracao_treinamento.tex",
        "disponibilidade_medicoes_computacionais.json",
        "manifesto_sha256.json",
    }
    nomes_gerados = {p.name for p in saida.iterdir()}
    assert esperados <= nomes_gerados
    assert "comparacao_timesnet_dilatedrnn_por_localidade.tex" not in nomes_gerados
    assert "epocas_parametros_tempos.csv" not in nomes_gerados
    assert "epocas_parametros_tempos.tex" not in nomes_gerados
    assert "medicoes_computacionais.csv" not in nomes_gerados
    assert "medicoes_computacionais.tex" not in nomes_gerados

    desempenho = pd.read_csv(saida / "desempenho_macro.csv")
    assert desempenho["MAE_wm2"].tolist() == sorted(desempenho["MAE_wm2"].tolist())
    comparacao = pd.read_csv(saida / "comparacao_timesnet_dilatedrnn_resumo.csv").iloc[0]
    assert comparacao["vitorias_locais_timesnet"] == 1
    assert comparacao["vitorias_locais_dilatedrnn"] == 1
    assert comparacao["empates_locais"] == 0

    ganho = pd.read_csv(saida / "caso_maior_ganho_timesnet.csv").iloc[0]
    deficit = pd.read_csv(saida / "caso_maior_deficit_timesnet.csv").iloc[0]
    meteorologico = pd.read_csv(
        saida / "caso_meteorologico_independente.csv"
    ).iloc[0]
    assert ganho["localidade"] == LOCAIS[0]
    assert ganho["origem"] == "2024-01-02"
    assert not bool(ganho["condicao_adversa_independente"])
    assert ganho["ganho_timesnet_vs_dilatedrnn_wm2"] == pytest.approx(15.0)
    assert deficit["localidade"] == LOCAIS[0]
    assert deficit["origem"] == "2024-01-01"
    assert bool(deficit["condicao_adversa_independente"])
    assert deficit["ganho_timesnet_vs_dilatedrnn_wm2"] == pytest.approx(-25.0)
    assert meteorologico["localidade"] == LOCAIS[0]
    assert meteorologico["data_local"] == "2024-01-02"
    assert not bool(meteorologico["erros_modelos_usados_na_selecao"])
    assert not bool(meteorologico["alegacao_causal"])
    regra = json.loads((saida / "regra_selecao_casos.json").read_text(encoding="utf-8"))
    assert regra["ghi_usado_para_classificar_chuva_ou_nuvens"] is False
    assert regra["meteorologia_usada_na_selecao_dos_extremos"] is False
    assert regra["alegacao_causal"] is False
    assert regra["unidade_extremo"] == "site_forecast_origin_cumulative_horizon"
    assert "meteorology excluded" in ganho["universo_selecao"]

    contrastes = pd.read_csv(saida / "contrastes_por_origem_horizonte.csv")
    assert len(contrastes) == 4
    assert set(contrastes["origem"]) == {"2024-01-01", "2024-01-02"}

    latex_desempenho = (saida / "desempenho_macro.tex").read_text(encoding="utf-8")
    assert "Macro test MAE" in latex_desempenho
    assert "Task" in latex_desempenho
    assert "Resolution" in latex_desempenho
    assert "Desempenho" not in latex_desempenho
    assert "Horizonte" not in latex_desempenho
    assert latex_desempenho.count(r" \\") == 2
    assert "Factory \\& North" in (saida / "caso_maior_ganho_timesnet.tex").read_text(
        encoding="utf-8"
    )

    disponibilidade = json.loads(
        (saida / "disponibilidade_medicoes_computacionais.json").read_text(
            encoding="utf-8"
        )
    )
    assert disponibilidade["instrumentacao_computacional_disponivel"] is False
    assert all(
        not detalhe["available"]
        for detalhe in disponibilidade["medicoes"].values()
    )

    manifesto_saida = json.loads((saida / "manifesto_sha256.json").read_text(encoding="utf-8"))
    assert manifesto_saida["N_arquivos"] == len(manifesto_saida["arquivos"])
    for item in manifesto_saida["arquivos"]:
        arquivo = saida / item["arquivo"]
        assert arquivo.stat().st_size == item["bytes"]
        assert sha256_arquivo(arquivo) == item["sha256"]


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("modo_execucao", "smoke", "smoke/nao completo"),
        ("etapa", "em_execucao", "Execucao incompleta"),
        ("resultado_publicavel", False, "resultado_publicavel=true"),
    ],
)
def test_recusa_status_smoke_ou_incompleto(
    tmp_path: Path, campo: str, valor: object, trecho: str
) -> None:
    tarefa = _criar_tarefa_diaria(tmp_path / "entradas")
    status_path = tarefa / "status_execucao.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status[campo] = valor
    _json(status_path, status)
    contexto, manifesto_contexto = _criar_contexto(tmp_path)

    with pytest.raises(ArtefatoNaoPublicavelError, match=trecho):
        gerar_artefatos_artigo_unificado(
            pastas_tarefas=[tarefa],
            caminho_contexto_nasa=contexto,
            caminho_manifesto_contexto_nasa=manifesto_contexto,
            pasta_saida=tmp_path / "saida",
        )


def test_recusa_arquivo_que_diverge_do_manifesto(tmp_path: Path) -> None:
    tarefa = _criar_tarefa_diaria(tmp_path / "entradas")
    with (tarefa / "metricas_macro.csv").open("a", encoding="utf-8") as arquivo:
        arquivo.write("\n")
    contexto, manifesto_contexto = _criar_contexto(tmp_path)

    with pytest.raises(ArtefatoNaoPublicavelError, match="(Tamanho|SHA-256) divergente"):
        gerar_artefatos_artigo_unificado(
            pastas_tarefas=[tarefa],
            caminho_contexto_nasa=contexto,
            caminho_manifesto_contexto_nasa=manifesto_contexto,
            pasta_saida=tmp_path / "saida",
        )


def test_aceita_extensao_horaria_e_declara_limitacao_de_uma_semente(
    tmp_path: Path,
) -> None:
    tarefa = _criar_tarefa_horaria(tmp_path / "entradas")
    contexto, manifesto_contexto = _criar_contexto(tmp_path)
    saida = tmp_path / "saida"

    resumo = gerar_artefatos_artigo_unificado(
        pastas_tarefas=[tarefa],
        caminho_contexto_nasa=contexto,
        caminho_manifesto_contexto_nasa=manifesto_contexto,
        pasta_saida=saida,
        chunksize=2,
    )

    assert resumo["limitacoes"] == [
        "extensao_horaria_com_uma_semente_seed_42;sem_variabilidade_entre_sementes"
    ]
    desempenho = pd.read_csv(saida / "desempenho_macro.csv")
    assert set(desempenho["N_sementes"]) == {1}
    assert desempenho["limitacao_sementes"].str.contains("uma_semente").all()
    variabilidade = pd.read_csv(saida / "variabilidade_sementes.csv")
    assert set(variabilidade["N_sementes"]) == {1}
    assert variabilidade["MAE_wm2_desvio_padrao"].isna().all()
    configuracao = pd.read_csv(saida / "configuracao_treinamento.csv")
    assert "N_parametros_treinaveis" not in configuracao.columns
    assert "tempo_treinamento_s" not in configuracao.columns
    assert "tempo_inferencia_s" not in configuracao.columns
    assert not (saida / "medicoes_computacionais.csv").exists()
    disponibilidade = json.loads(
        (saida / "disponibilidade_medicoes_computacionais.json").read_text(
            encoding="utf-8"
        )
    )
    assert disponibilidade["instrumentacao_computacional_disponivel"] is False
