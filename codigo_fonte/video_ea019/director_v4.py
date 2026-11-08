"""Build the continuous, camera-led 415-second film, with native 3D labels."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from blender_pilot import setup,frame
from render_style_v3 import apply_style
from common_v4 import rgba

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v4'
QA={2:[1,6,11,16,21,26,32],3:[3,9,15,19],4:[4,9,16,24,33,38],
    5:[2.5,8,13.5,18.5,23.5,30],6:[4,10,16,22,29,35,39],
    7:[3,9,16,22,27,33,37,43,47,53,59,63,68.5,73],8:[3,8,12,17,23,27,32],
    9:[3,8,12,16.5,23,28],10:[5,16,25,34,42,48,55],11:[1.7,7,15],12:[3,7.5,12],13:[3,7]}

def style(scene,chapter):
    metadata=apply_style(scene,chapter)
    shade=scene.display.shading
    shade.show_specular_highlight=True
    shade.studiolight_rotate_z=.8
    shade.studiolight_background_alpha=0
    shade.show_shadows=True;shade.show_cavity=True
    shade.curvature_ridge_factor=1.4;shade.curvature_valley_factor=1.0
    # Brighten opaque surfaces that came from the original graphite maquettes.
    for mat in bpy.data.materials:
        code=mat.get('design_srgb_hex')
        if code:
            mat.diffuse_color=rgba(code)
        elif mat.get('ea019_style_v3_srgb')=='#171C22':
            mat.diffuse_color=rgba('#344456')
        mat.roughness=.32;mat.metallic=.2
    scene.camera.data.dof.use_dof=False
    metadata.update({'version':4,'perspective_camera':True,'specular_highlights':True,'no_fixed_headers':True})
    return metadata

def build(chapter,duration,scene):
    if chapter<=6:
        from scenes_story_v4 import build_story_v4
        return build_story_v4(chapter,duration,scene)
    if chapter==7:
        from scenes_networks_v4 import build_networks_v4
        return build_networks_v4(duration)
    from scenes_analysis_v4 import build_analysis_v4
    return build_analysis_v4(chapter,duration,scene)

def main():
    p=argparse.ArgumentParser();p.add_argument('--index',type=int,nargs='*');p.add_argument('--qa',action='store_true')
    p.add_argument('--render',action='store_true');p.add_argument('--qa-percent',type=int,default=100)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    (OUT/'cenas').mkdir(parents=True,exist_ok=True);(OUT/'qa_3d').mkdir(exist_ok=True)
    plan=json.loads((OUT/'plano_video_v4.json').read_text(encoding='utf-8'))
    entries=[];bpy.context.preferences.filepaths.save_version=0
    for chapter in plan['chapters']:
        chapter={**chapter,'start_seconds':chapter['start'],'end_seconds':chapter['end'],'duration_seconds':chapter['duration']}
        n=chapter['id']
        if a.index and n not in a.index:continue
        d=chapter['duration_seconds']
        scene=setup(SimpleNamespace(engine='BLENDER_EEVEE_NEXT',samples=2,resolution_percentage=100))
        scene.name=f'EA019 filme v4 · {n:02d}'
        info=build(n,d,scene);scene.frame_end=round(d*30);scene.render.filepath=str(OUT/'cenas'/f'cena_{n:02d}_3d.mp4')
        render_style=style(scene,n);scene.frame_set(1)
        blend=OUT/'cenas'/f'cena_{n:02d}.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        if a.qa:
            old=scene.render.filepath;scene.render.image_settings.file_format='PNG';scene.render.resolution_percentage=a.qa_percent
            for t in QA[n]:
                scene.frame_set(frame(t));scene.render.filepath=str(OUT/'qa_3d'/f'cena_{n:02d}_t{str(t).replace(".","_")}.png')
                bpy.ops.render.render(write_still=True)
            scene.render.image_settings.file_format='FFMPEG';scene.render.resolution_percentage=100;scene.render.filepath=old
        if a.render:bpy.ops.render.render(animation=True)
        entry={**chapter,'blend':str(blend),'raw_mp4':scene.render.filepath,'frame_count':round(d*30),
               'rendered':bool(a.render),'scene_metadata':info,'render_style':render_style,'qa_times':QA[n]}
        (OUT/'cenas'/f'cena_{n:02d}_manifesto.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        entries.append(entry);print('V4_CHAPTER '+str(n),flush=True)
    manifest={'version':4,'duration_seconds':415,'fps':30,'frame_count':12450,'resolution':[1920,1080],
      'chapters':entries,'all_prepared':len(entries)==12,'full_rendered':len(entries)==12 and all(e['rendered'] for e in entries),
      'camera_footage_included':False,'narration_recorded':False,'fixed_headers':False,'source_banners':False}
    name='manifesto_producao_v4.json' if not a.index else 'manifesto_parcial_'+('_'.join(map(str,a.index)))+'.json'
    (OUT/name).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('V4_PREPARED '+str(len(entries)),flush=True)

if __name__=='__main__':main()
