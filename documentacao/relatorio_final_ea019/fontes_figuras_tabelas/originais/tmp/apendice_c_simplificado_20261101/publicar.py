from pathlib import Path
import hashlib,json,shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
DEST=ROOT/'documentacao/relatorio_final_ea019'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((HERE/'verificacao_e_mapa.json').read_text(encoding='utf-8'))
independent=json.loads((HERE/'auditoria_independente.json').read_text(encoding='utf-8'))
visual=json.loads((HERE/'qa_visual.json').read_text(encoding='utf-8'))
assert independent['passed'] and all(independent['checks'].values())
assert visual['passed'] and not visual['blocking_defects']
docx=HERE/(NAME+'.docx');pdf=HERE/'render-v1'/(NAME+'.pdf')
assert sha(docx)==report['docx_sha256']==independent['target_sha256']
assert sha(pdf)==report['pdf_sha256']
assert sha(DEST/docx.name)==sha(HERE/'antes.docx'), 'O Word principal foi alterado externamente.'
assert sha(DEST/pdf.name)==sha(HERE/'antes.pdf'), 'O PDF principal foi alterado externamente.'
for src in [docx,pdf]:
    target=DEST/src.name
    shutil.copy2(src,target)
    assert sha(src)==sha(target)
report['published_docx']=str(DEST/docx.name)
report['published_pdf']=str(DEST/pdf.name)
report['complete_change_review']=str(HERE/'alteracoes_completas.html')
report['visual_review_passed']=True
(HERE/'verificacao_final.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'published':True,'pages':report['pages_after'],'appendix_pages':report['appendix_pages_after'],
                  'unchanged_pages_except_toc':'1-33','text_replacements_in_appendix':7,'removed_paragraphs_in_appendix':31}))
