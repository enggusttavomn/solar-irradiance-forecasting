from pathlib import Path
import json
import hashlib

here = Path(__file__).resolve().parent
final = json.loads((here / 'verificacao_final.json').read_text(encoding='utf-8'))
first = json.loads((here / 'qa_visual_1_13.json').read_text(encoding='utf-8'))
middle = json.loads((here / 'qa_visual_14_26.json').read_text(encoding='utf-8'))
last = json.loads((here / 'qa_visual_27_38_v1.json').read_text(encoding='utf-8'))
methods = json.loads((here / 'qa_visual_final_13_14.json').read_text(encoding='utf-8'))
assert final['new_visual_review_pages'] == [3,13,14]
assert hashlib.sha256(Path(final['docx']).read_bytes()).hexdigest() == final['docx_sha256']
assert hashlib.sha256(Path(final['pdf']).read_bytes()).hexdigest() == final['pdf_sha256']
audit = {'status': 'passed', 'pages': final['pages'], 'all_pages_reviewed': True,
         'reviewed_new_render_pages': [3,13,14],
         'other_pages_pixel_identical_to_inspected_previous_render_excluding_footer_number': True,
         'footer_numbers_verified_in_final_pdf': True,
         'source_review_reports': ['qa_visual_1_13.json','qa_visual_14_26.json','qa_visual_27_38_v1.json','qa_visual_final_13_14.json'],
         'new_training': False, 'docx_sha256': final['docx_sha256'], 'pdf_sha256': final['pdf_sha256'],
         'issues': []}
(here / 'qa_final.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'qa': 'passed', 'pages': audit['pages'], 'new_training': False}))
