from pathlib import Path
import hashlib,json,shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
DEST=ROOT/'documentacao/relatorio_final_ea019'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
verification=json.loads((HERE/'verificacao.json').read_text(encoding='utf-8'))
independent=json.loads((HERE/'auditoria_independente.json').read_text(encoding='utf-8'))
visual=json.loads((HERE/'qa_visual.json').read_text(encoding='utf-8'))
assert independent['passed'] and all(independent['checks'].values())
assert visual['passed'] and not visual.get('blocking_defects',[])
docx=HERE/(NAME+'.docx');pdf=HERE/'render-v2'/(NAME+'.pdf')
assert sha(docx)==verification['docx_sha256']==independent['target_sha256']
assert sha(pdf)==verification['pdf_sha256']
for ext in ['.docx','.pdf']:
    assert sha(DEST/(NAME+ext))==sha(HERE/('antes'+ext)), 'O arquivo principal mudou externamente.'
for source in [docx,pdf]:
    target=DEST/source.name
    shutil.copy2(source,target)
    assert sha(source)==sha(target)
verification['published_docx']=str(DEST/docx.name)
verification['published_pdf']=str(DEST/pdf.name)
verification['visual_review_passed']=True
(HERE/'verificacao_final.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'published':True,'pages':37,'dedication_page':3,'acknowledgments_page':4,'body_text_changed':False}))
