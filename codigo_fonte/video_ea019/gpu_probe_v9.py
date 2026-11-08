import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,gpu
from common_v7 import setup,box,surface,ROOT
scene=setup(1,16,100)
box('Teste GPU',(0,0,3),(5,2,2),surface('Teste matte',(.2,.6,.7,1)))
scene.render.image_settings.file_format='PNG'
out=ROOT/'documentacao/relatorio_final_ea019/video/completo_v9';out.mkdir(parents=True,exist_ok=True)
scene.render.filepath=str(out/'teste_gpu_v9.png')
t=time.perf_counter();bpy.ops.render.render(write_still=True)
r={'blender':bpy.app.version_string,'engine':scene.render.engine,
 'renderer':gpu.platform.renderer_get(),'vendor':gpu.platform.vendor_get(),
 'version':gpu.platform.version_get(),'backend':gpu.platform.backend_type_get(),
 'render_seconds':time.perf_counter()-t,'resolution':[1920,1080],'samples':16,
 'eevee_uses_graphics_device':True}
(out/'verificacao_gpu_v9.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print('V9_GPU '+json.dumps(r),flush=True)
