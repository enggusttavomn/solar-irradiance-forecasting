"""Empacota fontes preservadas; não executa geradores nem modifica o relatório.

Os mapas de proveniência são a entrada auditada deste utilitário de entrega.
Execute na raiz do projeto com Python 3.12 ou posterior.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import html
import json
import mimetypes
from pathlib import Path
import shutil
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MAPS = ROOT / "tmp/proveniencia_elementos_relatorio"
OUT = ROOT / "documentacao/relatorio_final_ea019/fontes_figuras_tabelas"
ZIP = OUT.parent / "Scripts_Figuras_Imagens_Tabelas_Relatorio.zip"
REPORT = OUT.parent / "Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf"
DOCX = REPORT.with_suffix(".docx")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    figures = load(MAPS / "figuras_mapa.json")
    tables = load(MAPS / "tabelas_mapa.json")
    pipeline = load(MAPS / "pipeline_dependencias.json")
    assert len(figures["figures"]) == 9
    assert len(tables["tabelas"]) == 17
    assert all(f["binary_match_verified"] for f in figures["figures"])
    assert all(t["verificacao"]["conteudo_reconstruido_confere_integralmente_com_docx_atual"]
               for t in tables["tabelas"])
    before = {str(p.relative_to(ROOT)): sha(p) for p in (REPORT, DOCX)}
    # Evita misturar uma entrega nova com arquivos de uma execução anterior.
    if (OUT.exists() and any(OUT.iterdir())) or ZIP.exists():
        raise FileExistsError("A entrega já existe; escolha outro destino para uma nova edição.")
    OUT.mkdir(parents=True, exist_ok=True)
    originals = OUT / "originais"
    files = {}
    omitted = []

    def copy_original(rel: str, role: str, expected: str | None = None):
        rel = Path(rel).as_posix()
        src = (ROOT / rel).resolve()
        assert src.is_relative_to(ROOT), rel
        if not src.is_file():
            raise FileNotFoundError(src)
        digest = sha(src)
        if expected:
            assert digest == expected, rel
        if rel not in files:
            dst = originals / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            assert sha(dst) == digest
            files[rel] = {"original": rel, "arquivo_no_pacote": dst.relative_to(OUT).as_posix(),
                          "bytes": src.stat().st_size, "sha256": digest, "papeis": []}
        if role not in files[rel]["papeis"]:
            files[rel]["papeis"].append(role)

    script_paths = set(pipeline["package_script_paths"]) | {
        e["path"] if isinstance(e, dict) else e for e in figures["scripts_to_package"]}
    for t in tables["tabelas"]:
        script_paths.add(t["script_path"])
        script_paths.update(x["script_path"] for x in t["scripts_complementares"])
    for rel in sorted(script_paths):
        copy_original(rel, "script original / etapa histórica")
    for rel in pipeline["package_small_input_paths"]:
        copy_original(rel, "entrada ou registro preservado")
    for f in figures["figures"]:
        copy_original(f["asset"], f"PNG atual da Figura {f['number']}", f["asset_sha256"])
        if f["vector_asset"]:
            v = f["vector_asset"]
            copy_original(v["path"], f"SVG da Figura {f['number']}", v["sha256"])
        for entry in f["inputs"]:
            if entry["bytes"] > 5_000_000:
                omitted.append({**entry, "motivo": "Raster geográfico externo; caminho e hash registrados, arquivo grande fora do pacote."})
            else:
                copy_original(entry["path"], f"entrada da Figura {f['number']}", entry["sha256"])
    for t in tables["tabelas"]:
        for rel in t["fontes"]:
            copy_original(rel, f"fonte da Tabela {t['numero']}")
    template = "tmp/relatorio_final_ea019/modelo_referencia.docx"
    copy_original(template, "modelo institucional com os logotipos originais")
    # Guarda os três arquivos binários, distinguindo o cabeçalho inativo.
    with zipfile.ZipFile(DOCX) as archive:
        for logo in figures["unnumbered_images"]:
            raw = archive.read(logo["docx_media"])
            assert hashlib.sha256(raw).hexdigest() == logo["asset_sha256"]
            dst = OUT / "imagens_institucionais" / Path(logo["docx_media"]).name
            dst.parent.mkdir(exist_ok=True)
            dst.write_bytes(raw)

    # O diagnóstico também audita as demais tarefas. Inclui somente contratos,
    # rankings e pequenos logs de seleção; nenhum checkpoint ou previsão grande.
    base = ROOT / "resultados/quantizacao_todos_modelos_20260929"
    for regime in ("atual", "historico_1998_2022", "historico_curto_pareado"):
        for task in ("hourly_72_extension", "daily_30", "monthly_1", "monthly_6"):
            for model in ("transformer", "informer", "lstm"):
                folder = base / regime / task / model
                frozen = load(folder / "selecao_congelada.json")
                for name in ("selecao_congelada.json", "contrato_execucao.json"):
                    copy_original((folder / name).relative_to(ROOT).as_posix(), "contratos e auditoria dos registros")
                for variant in frozen["ranking"]:
                    for seed in variant["epocas"]:
                        path = folder / variant["nome"] / "selecao" / f"seed{seed}.csv"
                        copy_original(path.relative_to(ROOT).as_posix(), "log de seleção para auditoria do diagnóstico")
                        meta = path.with_suffix(".json")
                        if meta.exists():
                            copy_original(meta.relative_to(ROOT).as_posix(), "metadados do log de seleção")

    provenance = OUT / "proveniencia"
    provenance.mkdir()
    for name in ("figuras_mapa.json", "tabelas_mapa.json", "pipeline_dependencias.json",
                 "verificacao_rasterizador_novo.json"):
        shutil.copy2(MAPS / name, provenance / name)
    write_json(provenance / "entradas_externas_nao_incluidas.json", omitted)
    utility = OUT / "utilitarios"
    utility.mkdir()
    for name in ("rasterizar_svg_relatorio.cjs", "empacotar_fontes_elementos_relatorio.py"):
        shutil.copy2(ROOT / "codigo_fonte/publicacoes" / name, utility / name)

    def link_original(rel: str, label: str | None = None) -> str:
        return f'<a href="{quote("originais/" + rel, safe="/")}">{html.escape(label or rel)}</a>'

    def excerpt(rel: str, start: int, end: int) -> str:
        lines = (ROOT / rel).read_text(encoding="utf-8-sig").splitlines()
        assert 1 <= start <= end <= len(lines), (rel, start, end, len(lines))
        return "\n".join(f"{i:4d} | {lines[i-1]}" for i in range(start, end + 1))

    excerpt_dir = OUT / "trechos_por_elemento"
    excerpt_dir.mkdir()
    records = []
    text_index = ["FONTES DAS FIGURAS, IMAGENS E TABELAS DO RELATÓRIO EA019", "",
                  "9 figuras, 17 tabelas e 2 logotipos ativos. O terceiro logotipo é legado/inativo.",
                  "Abra INDICE.html para visualizar cada elemento e seu código.",
                  "Os trechos são referências com números de linha, não programas independentes.", ""]
    figure_sections, table_sections, logo_sections = [], [], []
    for kind, entries in (("Figura", figures["figures"]), ("Tabela", tables["tabelas"])):
        for entry in entries:
            n = entry.get("number", entry.get("numero"))
            title = entry.get("title", entry.get("titulo"))
            pages = [entry["page"]] if kind == "Figura" else entry["paginas_caption_pdf"]
            blocks = [{"script_path": entry["script_path"], "line_start": entry["line_start"],
                       "line_end": entry["line_end"],
                       "role": entry.get("function", entry.get("function_or_block"))}]
            if kind == "Figura":
                blocks += entry["supporting_scripts"]
            else:
                g = entry["gerador"]
                blocks += [{"script_path": g["script"], "line_start": g["helper_inicio"],
                            "line_end": g["helper_fim"], "role": "Função auxiliar que formata e insere a tabela"}]
                blocks += entry["scripts_complementares"]
            name = f"{kind}_{n:02d}.txt"
            chunks, code_html = [], []
            for block in blocks:
                rel, start, end = block["script_path"], block["line_start"], block["line_end"]
                role = block.get("role", block.get("function_or_block", "Apoio"))
                code = excerpt(rel, start, end)
                chunks.append(f"{role}\nArquivo original: {rel}\nLinhas: {start}–{end}\n\n{code}")
                code_html.append(f'<details><summary>{html.escape(role)} — linhas {start}–{end}</summary>'
                                 f'<p>{link_original(rel)}</p><pre>{html.escape(code)}</pre></details>')
            (excerpt_dir / name).write_text(
                f"{kind} {n} — {title}\nPágina(s) do PDF: {', '.join(map(str, pages))}\n\n"
                "TRECHOS PARA CONSULTA. Use os arquivos completos em originais/ para edição.\n"
                "Os números à esquerda são as linhas originais; este TXT não é executável.\n\n"
                + "\n\n".join(chunks) + "\n", encoding="utf-8")
            text_index += [f"{kind} {n} — {title}", f"Página(s): {pages}",
                           f"Original: {entry['script_path']} ({entry['line_start']}–{entry['line_end']})",
                           f"Trechos: trechos_por_elemento/{name}", ""]
            record = {"tipo": kind, "numero": n, "titulo": title, "paginas_pdf": pages,
                      "script_original": entry["script_path"], "linhas": [entry["line_start"], entry["line_end"]],
                      "trechos": f"trechos_por_elemento/{name}"}
            records.append(record)
            preview = ""
            if kind == "Figura":
                raw = (ROOT / entry["asset"]).read_bytes()
                preview = f'<img loading="lazy" alt="Figura {n}" src="data:image/png;base64,{base64.b64encode(raw).decode()}">'
                explanation = entry["source"] + " " + " ".join(entry["notes"])
            else:
                rows = entry["rows_canonicas"]
                preview = '<details><summary>Conferir conteúdo da tabela</summary><div class="scroll"><table>'
                for i, row in enumerate(rows):
                    tag = "th" if i == 0 else "td"
                    preview += '<tr>' + ''.join(f'<{tag}>{html.escape(str(c))}</{tag}>' for c in row) + '</tr>'
                preview += '</table></div></details>'
                explanation = entry["nota"]
            section = (f'<section id="{kind.lower()}{n}"><h3>{kind} {n} — {html.escape(title)}</h3>'
                       f'<p class="meta">PDF: página(s) {", ".join(map(str, pages))} · '
                       f'<a href="trechos_por_elemento/{name}">Trechos em TXT</a></p>{preview}'
                       f'<p>{html.escape(explanation)}</p>' + ''.join(code_html) + '</section>')
            (figure_sections if kind == "Figura" else table_sections).append(section)

    for i, logo in enumerate(figures["unnumbered_images"], 1):
        status = "Visível no relatório final" if logo["active_in_current_report"] else "Legado: cabeçalho inativo, não aparece no PDF"
        raw = (OUT / "imagens_institucionais" / Path(logo["docx_media"]).name).read_bytes()
        mime = mimetypes.guess_type(logo["docx_media"])[0]
        logo_sections.append(f'<section><h3>{html.escape(logo["title"])}</h3><p>{status}</p>'
                             f'<img class="logo" src="data:{mime};base64,{base64.b64encode(raw).decode()}" alt="Logotipo">'
                             f'<p>{html.escape(logo["source"])}</p><p>Modelo: {link_original(template)}.</p>'
                             f'<p>Importação: {link_original(logo["script_path"])} — linhas 14–38.</p></section>')
        text_index += [logo["title"], status, logo["source"], ""]

    readme = """FONTES DAS FIGURAS, IMAGENS E TABELAS — RELATÓRIO EA019

Abra INDICE.html. O índice é autocontido: as miniaturas e os trechos de código
podem ser consultados sem executar Python. Para abrir os scripts completos pelos
links, extraia o ZIP inteiro, preservando as pastas.

CONTEÚDO
- 9 figuras numeradas e 17 tabelas, identificadas por título e página do PDF.
- 26 arquivos TXT com os trechos específicos e seus auxiliares.
- originais/: scripts completos e entradas preservadas, com a hierarquia original.
- imagens_institucionais/: dois logos ativos e um logo legado/inativo.
- proveniencia/: mapas detalhados, dependências e verificações.
- utilitarios/: dois utilitários novos de entrega, separados das fontes históricas.
- MANIFESTO.json: caminho, tamanho e SHA-256 dos arquivos originais copiados.

COMO INTERPRETAR OS SCRIPTS
Várias figuras/tabelas compartilham o mesmo gerador. Os trechos TXT têm números
de linha para consulta e não são scripts independentes. Os arquivos completos
foram copiados sem alterar seu conteúdo. As tabelas são objetos do DOCX, não
imagens; as funções table/add_table montam e formatam suas células.

REPRODUÇÃO
Os scripts foram desenvolvidos em etapas. Muitos contêm caminhos da máquina
original e dependem de versões anteriores do documento. Não se oferece um
comando único para reconstruir o relatório atual. Consulte a ordem das etapas
em proveniencia/pipeline_dependencias.json e adapte os caminhos em uma cópia
isolada do projeto antes de executar os geradores ou editores históricos.
Os resultados, curvas e logs já existentes acompanham o pacote; não é necessário
treinar modelos para consultar o código. Os dois grandes rasters Köppen–Geiger
não acompanham o ZIP; seus caminhos, tamanhos e hashes estão registrados em
proveniencia/entradas_externas_nao_incluidas.json. O PNG exato do mapa utilizado
no relatório foi incluído. Mantenha os créditos de suas fontes.

Dependências dos geradores: Python com numpy, pandas, python-docx, lxml, Pillow,
pypdf e PyMuPDF; matplotlib/rasterio para o mapa; Node.js com sharp para SVG/PNG.
A exportação histórica do DOCX usou Microsoft Word no Windows e fontes Times
New Roman/Arial. Esses componentes não são distribuídos neste pacote.

UTILITÁRIOS NOVOS
rasterizar_svg_relatorio.cjs foi criado para converter SVGs preservados sem
executar o builder do relatório. Use --help para consultar seus argumentos.
As Figuras 7 e 8 foram testadas com ele e os PNGs resultantes coincidiram
integralmente com os atuais. Isso não é apresentado como o comando histórico.
empacotar_fontes_elementos_relatorio.py é apenas o montador desta entrega;
depende dos mapas de proveniência existentes no projeto de origem.

VERIFICAÇÃO
As 9 imagens numeradas correspondem byte a byte às imagens do DOCX atual.
As 996 células das 17 tabelas conferem com a reconstrução de suas fontes.
O relatório PDF e o DOCX de produção permaneceram inalterados ao empacotar.
Os scripts históricos não foram executados nesta preparação. A verificação
sintática e de hashes não equivale à execução integral do pipeline.
"""
    (OUT / "LEIA_ME.txt").write_text(readme, encoding="utf-8")
    (OUT / "INDICE.txt").write_text("\n".join(text_index), encoding="utf-8")
    nav = ' · '.join(f'<a href="#{r["tipo"].lower()}{r["numero"]}">{r["tipo"]} {r["numero"]}</a>' for r in records)
    document = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Scripts das figuras e tabelas — EA019</title>
<style>body{font:17px/1.6 system-ui,sans-serif;color:#17212b;background:#f2f5f8;margin:0}main{max-width:1080px;margin:auto;padding:28px 20px}h1{line-height:1.2}h2{margin-top:50px}a{color:#155f9c;overflow-wrap:anywhere}section{background:white;padding:24px;margin:22px 0;border:1px solid #dbe3ea;border-radius:12px}img{display:block;max-width:100%;max-height:700px;margin:20px auto;object-fit:contain}.logo{max-height:120px}summary{cursor:pointer;padding:12px 0;font-weight:600}pre{font:13px/1.6 Consolas,monospace;overflow:auto;background:#111b24;color:#e5eff6;padding:18px;border-radius:8px}nav{font-size:14px;line-height:2.2}.meta{color:#526372;font-size:14px}.scroll{overflow:auto}table{border-collapse:collapse;font-size:13px}th,td{border:1px solid #cbd6df;padding:7px;text-align:left}th{background:#edf3f8}</style><main>
<h1>Scripts de cada figura, imagem e tabela</h1>
<p>Relatório final EA019: <strong>9 figuras e 17 tabelas</strong>. Cada elemento abaixo traz seu código específico, a página do PDF e o arquivo gerador completo.</p>
<p>Vários elementos compartilham o mesmo script. Os trechos são referências numeradas; para editar, use o arquivo original completo. Os logotipos são imagens institucionais herdadas do modelo.</p>
<p><a href="LEIA_ME.txt">Como usar o pacote e suas dependências</a> · <a href="INDICE.txt">Índice em texto</a> · <a href="MANIFESTO.json">Manifesto de arquivos</a></p><nav>'''
    document += nav + '</nav><h2>Figuras</h2>' + ''.join(figure_sections)
    document += '<h2>Tabelas</h2>' + ''.join(table_sections)
    document += '<h2>Imagens institucionais</h2>' + ''.join(logo_sections)
    document += '<p>Fontes históricas preservadas. O relatório de produção não foi alterado.</p></main></html>'
    (OUT / "INDICE.html").write_text(document, encoding="utf-8")
    write_json(OUT / "MANIFESTO.json", {"relatorios_de_referencia_sha256": before,
               "elementos": records, "arquivos_originais": list(files.values()),
               "entradas_grandes_nao_incluidas": omitted})

    parsed = 0
    for path in originals.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        parsed += 1
    assert before == {str(p.relative_to(ROOT)): sha(p) for p in (REPORT, DOCX)}
    members = sorted(p for p in OUT.rglob("*") if p.is_file())
    write_json(OUT / "VERIFICACAO.json", {"status": "concluido", "figuras": 9, "tabelas": 17,
               "celulas_tabelas_conferidas": sum(t['verificacao']['celulas_verificadas'] for t in tables['tabelas']),
               "scripts_historicos": len(script_paths), "scripts_python_com_sintaxe_verificada": parsed,
               "originais_copiados_e_hashes_conferidos": len(files),
               "relatorio_pdf_e_docx_inalterados": True, "geradores_historicos_executados": False,
               "utilitario_raster_testado_figuras_7_8": load(MAPS / 'verificacao_rasterizador_novo.json')})
    members.append(OUT / "VERIFICACAO.json")
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in members:
            archive.write(path, path.relative_to(OUT).as_posix())
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(members)
        for path in members:
            assert hashlib.sha256(archive.read(path.relative_to(OUT).as_posix())).hexdigest() == sha(path)
    print(json.dumps({"zip": str(ZIP), "zip_bytes": ZIP.stat().st_size, "zip_sha256": sha(ZIP),
                      "indice": str(OUT / "INDICE.html"), "arquivos_zip": len(members),
                      "scripts": len(script_paths), "fontes_copiadas": len(files)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
