"""Pure Python orchestration helpers; no Blender import."""
import ast,hashlib,json,os,time
from pathlib import Path
from config_v9 import *
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for attempt in range(200):
        try:os.replace(tmp,path);return
        except PermissionError:time.sleep(.05)
    raise RuntimeError('Cannot replace '+str(path))
def read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return default
def current_sources(module):
    # Evaluate only these two known, self-authored pure functions, not bpy code.
    tree=ast.parse((ROOT/'codigo_fonte/video_ea019/director_v9.py').read_text(encoding='utf-8'))
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('sha','sources')]
    ns={'Path':Path,'ROOT':ROOT,'MODELS_SOURCE':MODELS_SOURCE,'hashlib':hashlib,'json':json}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),'director_v9_fingerprint','exec'),ns)
    return ns['sources'](module)
