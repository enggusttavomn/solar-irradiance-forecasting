"""One clean physical factory still, keeping the approved V9 camera and light."""
from pathlib import Path
import hashlib,json
import bpy,gpu

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'documentacao/relatorio_final_ea019/video/completo_v9/cenas/conclusao_v9.blend'
OUT=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v10/encerramento'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    before=sha(SOURCE)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene=bpy.context.scene;scene.frame_set(1486)
    names=['V6 generic EV manufacturing architecture','V6 optional solar parking application']
    physical=set()
    for name in names:
        collection=bpy.data.collections.get(name)
        if collection is None:raise ValueError('Missing approved physical collection '+name)
        physical.update(collection.all_objects)
    keep=set(physical)
    keep.update(o for o in scene.objects if o.type in {'CAMERA','LIGHT'})
    for o in list(keep):
        parent=o.parent
        while parent:
            keep.add(parent);parent=parent.parent
    removed=[]
    for o in list(scene.objects):
        if o not in keep:
            removed.append({'name':o.name,'type':o.type})
            bpy.data.objects.remove(o,do_unlink=True)
    remaining_fonts=[o.data.body for o in scene.objects if o.type=='FONT']
    if remaining_fonts!=['ELECTRIC VEHICLE MANUFACTURING']:
        raise ValueError('Unexpected remaining font: '+repr(remaining_fonts))
    scene.render.engine='BLENDER_EEVEE_NEXT';scene.eevee.taa_render_samples=16
    scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    target=OUT/'fabrica_encerramento_limpa_v10.png';scene.render.filepath=str(target)
    bpy.ops.render.render(write_still=True)
    renderer=gpu.platform.renderer_get()
    if 'Arc' not in renderer:raise ValueError('Expected Intel Arc, found '+renderer)
    after=sha(SOURCE)
    if before!=after:raise ValueError('Original blend changed')
    report={'status':'awaiting_sampled_visual_review','source':str(SOURCE.relative_to(ROOT)),
        'source_sha256_before':before,'source_sha256_after':after,'source_modified':False,
        'source_chapter_local_seconds':49.5,'source_frame':1486,'source_animation_seconds':557.5,
        'path':str(target.relative_to(ROOT)),'width':1920,'height':1080,'sha256':sha(target),
        'kept_physical_collections':names,'physical_object_count':len(physical),
        'remaining_font_bodies':remaining_fonts,'removed_nonphysical_objects':removed,
        'camera_pose_preserved':True,'lights_preserved':True,'samples':16,'render_count':1,
        'gpu':{'renderer':renderer,'vendor':gpu.platform.vendor_get(),'backend':gpu.platform.backend_type_get(),
               'engine':scene.render.engine},'automatically_approved':False,
        'no_new_results_or_claims_added':True}
    (OUT/'fabrica_encerramento_limpa_v10.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V10_CLEAN_FACTORY_STILL_RENDERED',flush=True)

if __name__=='__main__':main()
