"""Record sampled manual scene approvals; never grants approval by itself."""
import argparse
from datetime import datetime,timezone
from pipeline_v9 import *
def main():
    p=argparse.ArgumentParser();p.add_argument('chapters',nargs='+',choices=CHAPTERS)
    a=p.parse_args();path=OUT/'qa_aprovado_v9.json';gates=read(path,{})
    for name in a.chapters:
        if name=='resultados':continue
        record=read(OUT/'cenas'/f'{name}_manifesto_v9.json',{})
        if not record:raise ValueError('Preflight manifest missing '+name)
        key,values=current_sources(CHAPTERS[name]['module'])
        changed=[x for x,v in record['source_hashes'].items() if values.get(x)!=v]
        visual_changed=[x for x in changed if not x.endswith('director_v9.py')]
        if visual_changed:raise ValueError('Scene sources changed after preflight '+str(visual_changed))
        gates[name]={'approved':True,'automatically_approved':False,
          'scope':'Root manual sampled Full HD visual and scientific preflight',
          'reviewed_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':values,
          'source_fingerprint':key,'nonvisual_director_changes_after_preflight':changed}
    write_json(path,gates);print('V9_APPROVED '+','.join(a.chapters),flush=True)
if __name__=='__main__':main()
