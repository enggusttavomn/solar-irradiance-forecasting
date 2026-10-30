from datetime import datetime, timezone
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import digest

SOURCE = WORK / 'revisao_v4.pdf'
DESTINATION = ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
RECORDS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_analise_compacta_20261012'
report = json.loads(SOURCE.with_suffix('.verificacao.json').read_text(encoding='utf-8'))
manifest = json.loads((WORK / 'manifesto_v4.json').read_text(encoding='utf-8'))
approval = json.loads((WORK / 'revisao_visual.json').read_text(encoding='utf-8'))
assert report['ok'] and report['paginas'] == 10
assert approval['ok'] and approval['paginas_revisadas'] == list(range(1, 11))
assert digest(SOURCE) == report['sha256'] == manifest['pdf']['sha256'] == approval['sha256']
assert all(digest(path) == expected for path, expected in manifest['fontes_sha256'].items())
others = [ROOT / 'output/pdf/tabela_resultados_ghi_2024.pdf', ROOT / 'output/pdf/tabela_resultados_ghi_1998_2022.pdf']
other_hashes = {str(path): digest(path) for path in others}
assert all(digest(path) == digest(ROOT / 'documentacao' / path.name) for path in others)
RECORDS.mkdir(exist_ok=True)
backup = RECORDS / 'compacto_anterior_20_paginas.pdf'
previous_sha = digest(DESTINATION)
if previous_sha != report['sha256']:
    if backup.exists():
        assert digest(backup) == previous_sha
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
manifest['versao_anterior'] = {'path': str(backup), 'sha256': digest(backup), 'paginas': 20}
for name, value in [('manifesto.json', manifest), ('verificacao.json', report), ('revisao_visual.json', approval)]:
    (RECORDS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
receipt = {'entregue_em_utc': datetime.now(timezone.utc).isoformat(), 'pdf': manifest['pdf'],
           'pasta': str(DESTINATION.parent), 'outros_pdfs_preservados': other_hashes,
           'reducao_paginas': '20 para 10', 'revisao_visual_aprovada': True,
           'valores_conferidos_csv': report['celulas_numericas_conferidas_csv'],
           'texto_em_terceira_pessoa': True, 'escolhas_validacao_preservadas': True,
           'gerador': str(ROOT / 'scripts/gerar_pdf_quantizacao_analise_compacta.py')}
(RECORDS / 'entrega.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pdf': str(DESTINATION), 'paginas': 10, 'sha256': digest(DESTINATION),
                  'arquivos_na_pasta': sorted(path.name for path in DESTINATION.parent.glob('*.pdf')), 'ok': True}, ensure_ascii=False), flush=True)
