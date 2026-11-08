from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v9'
SECTIONS=[('introducao','intro_v9',52),('modelos','models_v9',60),
 ('geografia','geography_data_v9',60),('entradas_tarefas','inputs_tasks_v9',64),
 ('metodologia','methodology_v9',54),('quantizacao','quantization_v9',64),
 ('metricas','metrics_v9',66),('resultados','results_v8',88),
 ('conclusao','interpretation_v9',52)]
CHAPTERS={};start=0
for name,module,duration in SECTIONS:
    CHAPTERS[name]={'module':module,'duration':duration,'start':start,'end':start+duration}
    start+=duration
DURATION=start
assert DURATION==560
MODELS_SOURCE=ROOT/'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7/cenas/modelos_3d_v7.mp4'
RESULTS_SOURCE=ROOT/'documentacao/relatorio_final_ea019/video/completo_v8/cenas/resultados_3d_v8.mp4'
BLENDER=ROOT/'.tools/blender/blender-4.5.14-windows-x64/blender.exe'
PYTHON=ROOT/'.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe'
