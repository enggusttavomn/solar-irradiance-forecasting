from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import digest

DESTINATION = ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
RECORDS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_sem_abertura_20261012'
PREVIOUS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_analise_compacta_20261012'
SOURCE = WORK / 'revisao.pdf'
manifest = json.loads((WORK / 'manifesto.json').read_text(encoding='utf-8'))
report = json.loads((WORK / 'revisao.verificacao.json').read_text(encoding='utf-8'))
approval = json.loads((WORK / 'revisao_visual.json').read_text(encoding='utf-8'))
old_record = json.loads((PREVIOUS / 'manifesto.json').read_text(encoding='utf-8'))
assert report['ok'] and report['paginas'] == 9 and report['trechos_destacados_removidos']
assert report['corpos_das_oito_paginas_de_resultados_identicos']
assert approval['ok'] and approval['paginas_revisadas'] == list(range(1, 10))
assert digest(SOURCE) == manifest['pdf']['sha256'] == report['sha256'] == approval['sha256']
assert all(digest(path) == expected for path, expected in manifest['fontes_sha256'].items())
others = [ROOT / 'output/pdf/tabela_resultados_ghi_2024.pdf', ROOT / 'output/pdf/tabela_resultados_ghi_1998_2022.pdf']
other_hashes = {str(path): digest(path) for path in others}
assert all(digest(path) == digest(ROOT / 'documentacao' / path.name) for path in others)
RECORDS.mkdir(exist_ok=True)
backup = RECORDS / 'compacto_anterior_10_paginas.pdf'
if digest(DESTINATION) != report['sha256']:
    assert digest(DESTINATION) == old_record['pdf']['sha256']
    if backup.exists():
        assert digest(backup) == digest(DESTINATION)
    else:
        shutil.copy2(DESTINATION, backup)
    shutil.copy2(SOURCE, DESTINATION)
assert digest(DESTINATION) == report['sha256']
assert all(digest(path) == expected for path, expected in other_hashes.items())
images = RECORDS / 'paginas_verificadas'
shutil.copytree(Path(report['imagens']), images, dirs_exist_ok=True)
report['pdf'] = str(DESTINATION)
report['imagens'] = str(images)
manifest['pdf']['path'] = str(DESTINATION)
manifest['revisao_visual_pendente'] = False
manifest['revisao_visual_aprovada'] = True
manifest['versao_anterior'] = {'path': str(backup), 'sha256': digest(backup), 'paginas': 10}
for filename, value in [('manifesto.json', manifest), ('verificacao.json', report), ('revisao_visual.json', approval)]:
    (RECORDS / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
for filename in ('verificar_revisao.py', 'publicar_revisao.py'):
    shutil.copy2(WORK / filename, RECORDS / filename)
receipt = {'entregue_em_utc': datetime.now(timezone.utc).isoformat(), 'pdf': manifest['pdf'],
           'pasta': str(DESTINATION.parent), 'outros_pdfs_preservados': other_hashes,
           'removido': ['pagina de sintese', 'quadro agregado de quantizacao e textos destacados'],
           'cronologia': 'preservada ao final', 'resultados_preservados': True,
           'revisao_visual_aprovada': True}
(RECORDS / 'entrega.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pdf': str(DESTINATION), 'paginas': 9, 'sha256': digest(DESTINATION),
                  'arquivos_na_pasta': sorted(path.name for path in DESTINATION.parent.glob('*.pdf')), 'ok': True}, ensure_ascii=False), flush=True)
