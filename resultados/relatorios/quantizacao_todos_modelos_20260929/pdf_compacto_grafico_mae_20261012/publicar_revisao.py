from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import digest

SOURCE = WORK / 'revisao_v1.pdf'
DESTINATION = ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
RECORDS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_grafico_mae_20261012'
PREVIOUS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_sem_abertura_20261012'
manifest = json.loads((WORK / 'manifesto_v1.json').read_text(encoding='utf-8'))
report = json.loads((WORK / 'revisao_v1.verificacao.json').read_text(encoding='utf-8'))
approval = json.loads((WORK / 'revisao_visual.json').read_text(encoding='utf-8'))
previous = json.loads((PREVIOUS / 'manifesto.json').read_text(encoding='utf-8'))
assert report['ok'] and report['paginas'] == 10 and report['pontos_grafico_conferidos_csv'] == 132
assert report['menores_MAE_destacados_conferidos'] == 12 and report['primeira_nove_paginas_preservadas']
assert approval['ok'] and approval['paginas_revisadas'] == list(range(1, 11))
assert digest(SOURCE) == manifest['pdf']['sha256'] == report['sha256'] == approval['sha256']
assert all(digest(path) == expected for path, expected in manifest['fontes_sha256'].items())
others = [ROOT / 'output/pdf/tabela_resultados_ghi_2024.pdf', ROOT / 'output/pdf/tabela_resultados_ghi_1998_2022.pdf']
other_hashes = {str(path): digest(path) for path in others}
assert all(digest(path) == digest(ROOT / 'documentacao' / path.name) for path in others)
RECORDS.mkdir(exist_ok=True)
backup = RECORDS / 'compacto_anterior_9_paginas.pdf'
if digest(DESTINATION) != report['sha256']:
    assert digest(DESTINATION) == previous['pdf']['sha256']
    if backup.exists():
        assert digest(backup) == digest(DESTINATION)
    else:
        shutil.copy2(DESTINATION, backup)
    shutil.copy2(SOURCE, DESTINATION)
assert digest(DESTINATION) == report['sha256']
assert all(digest(path) == expected for path, expected in other_hashes.items())

images = RECORDS / 'paginas_verificadas'
shutil.copytree(Path(report['imagens']), images, dirs_exist_ok=True)
graph_dir = RECORDS / 'grafico_mae'
shutil.copytree(Path(manifest['grafico_MAE']['arquivos']['pdf']).parent, graph_dir, dirs_exist_ok=True)
for fmt, path in manifest['grafico_MAE']['arquivos'].items():
    manifest['grafico_MAE']['arquivos'][fmt] = str(graph_dir / Path(path).name)
manifest['grafico_MAE']['arquivos_sha256'] = {fmt: digest(path) for fmt, path in manifest['grafico_MAE']['arquivos'].items()}
(graph_dir / 'dados_grafico.json').write_text(json.dumps(manifest['grafico_MAE'], ensure_ascii=False, indent=2), encoding='utf-8')
report['pdf'], report['imagens'] = str(DESTINATION), str(images)
manifest['pdf']['path'] = str(DESTINATION)
manifest['revisao_visual_pendente'] = False
manifest['revisao_visual_aprovada'] = True
manifest['versao_anterior'] = {'path': str(backup), 'sha256': digest(backup), 'paginas': 9}
for filename, value in [('manifesto.json', manifest), ('verificacao.json', report), ('revisao_visual.json', approval)]:
    (RECORDS / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
for filename in ('verificar_revisao.py', 'publicar_revisao.py'):
    shutil.copy2(WORK / filename, RECORDS / filename)
shutil.copy2(ROOT / 'scripts/gerar_pdf_quantizacao_analise_compacta.py', RECORDS / 'gerador_pdf.py')
shutil.copy2(ROOT / 'scripts/gerar_grafico_mae_modelos.py', RECORDS / 'gerador_grafico.py')
receipt = {'entregue_em_utc': datetime.now(timezone.utc).isoformat(), 'pdf': manifest['pdf'],
           'pasta': str(DESTINATION.parent), 'outros_pdfs_preservados': other_hashes,
           'grafico_ultima_pagina': True, 'paineis': 4, 'modelos': 11, 'conjuntos': 3,
           'pontos_conferidos': 132, 'destaques_minimos': 12,
           'paginas_anteriores_preservadas': True, 'revisao_visual_aprovada': True}
(RECORDS / 'entrega.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pdf': str(DESTINATION), 'paginas': 10, 'sha256': digest(DESTINATION),
                  'arquivos_na_pasta': sorted(path.name for path in DESTINATION.parent.glob('*.pdf')), 'ok': True}, ensure_ascii=False), flush=True)
