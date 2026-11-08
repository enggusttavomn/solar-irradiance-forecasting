"""Procedural 3D scenes for the 6min55s EA019 animated cut.

Called by the Blender driver after it has prepared the stage, lights and camera.
Each builder uses local time 0..duration; all typography is composed by ASS.
No scene resets the stage, adds text objects, or starts a render.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

try:
    from .blender_pilot import (
        FPS, CYAN, GOLD, WHITE, SOFT, emission, surface, polyline, sphere,
        box, visible, reveal, wire_box, frame,
    )
except ImportError:
    from blender_pilot import (
        FPS, CYAN, GOLD, WHITE, SOFT, emission, surface, polyline, sphere,
        box, visible, reveal, wire_box, frame,
    )


CORAL = (1.0, .32, .25, 1)
VIOLET = (.54, .29, .93, 1)
MUTED = (.09, .16, .21, 1)


def _materials(prefix):
    return {
        'white': emission(prefix + ' · referência', WHITE, 1.6),
        'cyan': emission(prefix + ' · Transformer/previsão', CYAN, 1.7),
        'gold': emission(prefix + ' · destaque', GOLD, 1.35),
        'coral': emission(prefix + ' · LSTM', CORAL, 1.55),
        'violet': emission(prefix + ' · Informer', VIOLET, 1.55),
        'muted': emission(prefix + ' · contorno discreto', MUTED, .65),
        'glass': surface(prefix + ' · vidro escuro', (.024, .065, .085, 1),
                         metallic=.35, roughness=.24, transmission=.28),
    }


def _finish(name, duration, before):
    created = [o for o in bpy.data.objects if o not in before]
    for obj in created:
        if 'visible_start_seconds' not in obj:
            visible(obj, 0, duration)
        obj['ea019_scene'] = name
        obj['ea019_local_duration_seconds'] = duration
    return {'name': name, 'duration_seconds': duration,
            'fps': FPS, 'object_count': len(created),
            'text_objects': sum(o.type == 'FONT' for o in created)}


def _show(obj, start, end, *, pop=.35):
    visible(obj, start, end)
    if pop:
        target = obj.scale.copy()
        obj.scale = (.001, .001, .001)
        obj.keyframe_insert('scale', frame=frame(start))
        obj.scale = target
        obj.keyframe_insert('scale', frame=frame(min(end, start + pop)))
    return obj


def _trace(name, points, mat, start, end, draw=.7, radius=.012):
    obj = polyline(name, points, mat, radius)
    visible(obj, start, end)
    reveal(obj, start, min(draw, max(.01, end - start)))
    return obj


def _wire(name, a, b, mat, start, end, *, radius=.01, draw=.55):
    objects = wire_box(name, a, b, mat, radius)
    for i, obj in enumerate(objects):
        visible(obj, start, end)
        reveal(obj, start + (i % 4) * .035,
               min(draw, max(.01, end - start - .15)))
    return objects


def _move(obj, start, end, a, b):
    obj.location = a
    obj.keyframe_insert('location', frame=frame(start))
    obj.location = b
    obj.keyframe_insert('location', frame=frame(end))
    # Straight data flow, not a physical acceleration model.
    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        if hasattr(action, 'fcurves'):
            for curve in action.fcurves:
                if curve.data_path == 'location':
                    for key in curve.keyframe_points:
                        key.interpolation = 'LINEAR'


def _flow(name, a, b, material, start, end, period=3.2, radius=.045):
    obj = sphere(name, a, radius, material)
    visible(obj, start, end)
    for axis in range(3):
        driver = obj.driver_add('location', axis).driver
        driver.expression = (f'{a[axis]}+({b[axis]-a[axis]})*'
                             f'(((frame-{frame(start)})/{FPS*period})%1)')
    return obj


def _arrow(name, a, b, material, start, end, *, radius=.012, draw=.8):
    a_vec, b_vec = Vector(a), Vector(b)
    direction = (b_vec - a_vec).normalized()
    side = direction.cross(Vector((0, -1, 0)))
    if side.length < .1:
        side = direction.cross(Vector((0, 0, 1)))
    side.normalize()
    tip_a = b_vec - direction * .16 + side * .09
    tip_b = b_vec - direction * .16 - side * .09
    _trace(name + ' · eixo', [a, b], material, start, end, draw, radius)
    _trace(name + ' · ponta', [tuple(tip_a), b, tuple(tip_b)],
           material, start + min(.2, draw/2), end, .35, radius)


def _pulse(x, period=2.0):
    phase = (x + 4.3) % period
    day = period * .73
    return math.sin(math.pi * phase / day) ** 2 if phase < day else 0.0


def _quiet_panel(prefix, x0, x1, z0, z1, mats, start, end, *, depth=.12):
    _wire(prefix + ' · contorno', (x0, -.03, z0), (x1, depth, z1),
          mats['muted'], start, end, radius=.008)
    # Narrow edge strips suggest glass without obscuring the frontal data.
    for x in (x0, x1):
        obj = box(prefix + ' · lâmina', (x, .10, (z0+z1)/2),
                  (.045, .10, z1-z0), mats['glass'], .015)
        _show(obj, start, end, pop=.4)


def build_opening(duration=20):
    before = set(bpy.data.objects)
    mats = _materials('Abertura')
    faint_gold = emission('Abertura · curva dourada discreta', GOLD, .65)
    points = []
    for i in range(150):
        x = 1.2 + 3.2 * i / 149
        z = .45 + 1.9 * math.exp(-((x-3.05)/.59)**2)
        points.append((x, .48, z))
    curve = _trace('Abertura · perfil solar', points, faint_gold,
                   0, duration, draw=3.2, radius=.014)
    # This is illustrative light decoration, not an experimental forecast.
    plate = box('Abertura · base de vidro', (3.0, .57, .35),
                (2.7, .8, .08), mats['glass'], .035)
    _show(plate, 0, duration, pop=.7)
    _wire('Abertura · base luminosa', (1.65, .17, .31), (4.35, .97, .39),
          mats['muted'], 0, duration, radius=.007)
    marker = sphere('Abertura · luz em movimento', points[0], .038, faint_gold)
    visible(marker, 3.4, duration)
    for i in range(5):
        # Keyframed points follow the same smooth decorative solar profile.
        x = 1.2 + 3.2 * i / 4
        marker.location = (x, .48, .45 + 1.9*math.exp(-((x-3.05)/.59)**2))
        marker.keyframe_insert('location', frame=frame(3.4 + (duration-3.8)*i/4))
    return _finish('opening', duration, before)


def build_objective(duration=20):
    before = set(bpy.data.objects)
    mats = _materials('Objetivo')
    # An observed sequence is shared by all three conceptual routes.
    samples = [(-4.2 + 8.4*i/119, -.75,
                .43 + .55*_pulse(-4.2 + 8.4*i/119, 2.8)) for i in range(120)]
    _trace('Objetivo · histórico comum', samples, mats['white'],
           0, duration, draw=3.2, radius=.012)
    source = (0, -.7, .70)
    sink = (0, .65, 3.05)
    _show(sphere('Objetivo · origem', source, .085, mats['white']), 1, duration)
    for i, (x, color) in enumerate(((-3.0, 'coral'), (0.0, 'cyan'), (3.0, 'violet'))):
        center = (x, .0, 1.65)
        _arrow(f'Objetivo · entrada {i}', source, (x, -.08, 1.2),
               mats[color], 6+i*.3, duration, draw=1.2)
        node = box(f'Objetivo · representação {i}', center,
                   (.88, .60, .82), mats['glass'], .065)
        _show(node, 7+i*.3, duration)
        _wire(f'Objetivo · rede {i}', (x-.44, -.3, 1.24), (x+.44, .3, 2.06),
              mats[color], 7+i*.3, duration, radius=.012)
        _arrow(f'Objetivo · saída {i}', (x, .08, 2.1), sink,
               mats[color], 10+i*.3, duration, draw=1.2)
        _flow(f'Objetivo · fluxo {i}', source, (x, -.08, 1.2),
              mats[color], 8+i*.3, duration, period=4.0)
    _show(sphere('Objetivo · futuro comum', sink, .09, mats['white']), 12, duration)
    _trace('Objetivo · horizonte compartilhado', [(-1.1, .65, 3.05), (1.1, .65, 3.05)],
           mats['white'], 12, duration, draw=1.0)
    return _finish('objective', duration, before)


def build_tasks(duration=35):
    before = set(bpy.data.objects)
    mats = _materials('Tarefas')
    phases = [(0, 8, 1.8, 4.2), (8, 16, 3.0, 4.2),
              (16, 24, 4.7, 2.3), (24, duration, 4.7, 4.2)]
    for index, (start, end, period, future_end) in enumerate(phases):
        def height(x):
            return .50 + 1.65*_pulse(x, period)
        points = [(-4.2 + 4.5*i/119, 0, height(-4.2+4.5*i/119)) for i in range(120)]
        _trace(f'Tarefa {index} · eixo', [(-4.3, 0, .46), (4.3, 0, .46)],
               mats['muted'], start, end, draw=.7, radius=.008)
        _trace(f'Tarefa {index} · histórico', points, mats['white'],
               start+.15, end, draw=1.65, radius=.015)
        _wire(f'Tarefa {index} · janela observada', (-1.25, -.34, .48),
              (.3, .34, 2.75), mats['cyan'], start+1.2, end, radius=.009)
        _trace(f'Tarefa {index} · presente', [(.3, 0, .43), (.3, 0, 3.0)],
               mats['white'], start+2.0, end, draw=.45, radius=.006)
        dash_count = 18 if future_end > 3 else 10
        for j in range(dash_count):
            a = .42 + (future_end-.42)*j/dash_count
            b = a + (future_end-.42)*.58/dash_count
            points = [(a+(b-a)*k/3, 0, height(a+(b-a)*k/3)) for k in range(4)]
            _trace(f'Tarefa {index} · futuro {j}', points, mats['cyan'],
                   start+2.5+j*.09, end, draw=.40, radius=.015)
        _flow(f'Tarefa {index} · leitura do histórico', (-4.2, -.38, .5), (.3, -.38, .5),
              mats['white'], start+2, end, period=3.2, radius=.033)
    return _finish('tasks', duration, before)


def build_evaluation(duration=40):
    before = set(bpy.data.objects)
    mats = _materials('Avaliação')
    xs = [-3.4, -1.15, 1.15, 3.4]
    for i, x in enumerate(xs):
        start = i * 8
        block = box(f'Avaliação · etapa cronológica {i}', (x, .12, 1.45),
                    (1.64, .62, 1.1), mats['glass'], .055)
        _show(block, start, duration, pop=.65)
        _wire(f'Avaliação · bordas {i}', (x-.82, -.19, .9),
              (x+.82, .43, 2.0), mats['gold'] if i == 3 else mats['cyan'],
              start, duration, radius=.010)
        # Equal small samples stand for available observations, not epochs.
        for j in range(4):
            sample = sphere(f'Avaliação · amostra {i}-{j}',
                            (x-.45+j*.3, -.24, .65), .044,
                            mats['gold'] if i == 3 else mats['white'])
            _show(sample, start+.6+j*.12, duration)
        if i:
            a, b = (xs[i-1]+.9, 0, 1.45), (x-.9, 0, 1.45)
            _arrow(f'Avaliação · avanço {i}', a, b, mats['muted'],
                   start+.4, duration, draw=.65, radius=.010)
            _flow(f'Avaliação · passagem {i}', a, b,
                  mats['gold'] if i == 3 else mats['cyan'],
                  start+1.2, duration, period=3.8, radius=.035)
    # Refit receives a second frame: a fresh adjustment, not a frozen weight copy.
    _wire('Avaliação · novo ajuste', (.23, -.28, .82), (2.07, .50, 2.08),
          mats['muted'], 19, duration, radius=.006)
    return _finish('evaluation', duration, before)


def build_mae(duration=30):
    before = set(bpy.data.objects)
    mats = _materials('MAE')
    def reference(x):
        return 1.55 + .65*math.sin(x*1.25) + .15*math.cos(x*2.8)
    def forecast(x):
        return reference(x) + .22*math.sin(x*2.15+.7) + .12
    xs = [-4.1+5.4*i/159 for i in range(160)]
    _trace('MAE · referência conceitual', [(x, 0, reference(x)) for x in xs],
           mats['white'], 0, 14, draw=2.5, radius=.015)
    _trace('MAE · previsão conceitual', [(x, 0, forecast(x)) for x in xs],
           mats['cyan'], 1.3, 14, draw=2.5, radius=.015)
    for i in range(13):
        x = -3.9 + i*.41
        _trace(f'MAE · erro absoluto {i}', [(x, 0, reference(x)), (x, 0, forecast(x))],
               mats['gold'], 4+i*.4, 14, draw=.3, radius=.012)
    # Ten local metrics contribute with identical link width and marker size.
    center = (0, .15, 1.65)
    for i in range(10):
        x = -3.6 + (i % 5)*1.8
        z = .8 + (i//5)*1.65
        loc = (x, -.20, z)
        _show(sphere(f'MAE · localidade {i}', loc, .085, mats['white']),
              14+i*.10, 22)
        _trace(f'MAE · peso igual {i}', [loc, center], mats['muted'],
               16+i*.08, 22, draw=.6, radius=.008)
        bead = sphere(f'MAE · contribuição {i}', loc, .034, mats['gold'])
        visible(bead, 17+i*.12, 22)
        _move(bead, 17+i*.12, 20+i*.08, loc, center)
    _show(sphere('MAE · média macro', center, .12, mats['gold']), 19.5, 22)
    # Cumulative horizon: the entire interval is illuminated, not only its end.
    _trace('MAE · intervalo completo', [(-4.1, 0, 1.3), (4.1, 0, 1.3)],
           mats['muted'], 22, duration, draw=.7, radius=.014)
    _trace('MAE · acumulação de todos os passos', [(-4.1, -.02, 1.3), (4.1, -.02, 1.3)],
           mats['cyan'], 22.5, duration, draw=3.5, radius=.024)
    for i in range(13):
        x = -4.1 + i*8.2/12
        _trace(f'MAE · passo {i}', [(x, 0, 1.12), (x, 0, 1.48)],
               mats['white'], 22.5+i*.22, duration, draw=.2, radius=.008)
    _trace('MAE · abrangência cumulativa', [(-4.1, 0, 1.9), (-4.1, 0, 2.2),
                                          (4.1, 0, 2.2), (4.1, 0, 1.9)],
           mats['gold'], 26, duration, draw=1.1, radius=.010)
    return _finish('mae', duration, before)


def build_results(duration=60):
    before = set(bpy.data.objects)
    mats = _materials('Resultados')
    # Tables are drawn frontally in ASS.  No uncalibrated bars or sloped axes.
    _quiet_panel('Resultados · moldura principal', -4.45, 4.45, .52, 3.05,
                 mats, 0, 48)
    for x in (-4.45, 4.45):
        for z in (.52, 3.05):
            length = .40 if x < 0 else -.40
            _trace('Resultados · friso de canto', [(x, -.04, z), (x+length, -.04, z)],
                   mats['muted'], 0, 48, draw=.8, radius=.012)
    for i, start in enumerate((0, 12, 24, 36)):
        # Subtle border activation marks the next task without competing with data.
        _trace(f'Resultados · passagem {i}', [(-4.45, -.05, .52), (4.45, -.05, .52)],
               mats['muted'], start, min(48, start+12), draw=1.2, radius=.010)
    _quiet_panel('Resultados · diferença horária', -4.35, -.25, .7, 2.85,
                 mats, 48, duration)
    _quiet_panel('Resultados · diferença diária', .25, 4.35, .7, 2.85,
                 mats, 48, duration)
    # Small comparison guides remain ornamental, not representations of MAE.
    for x in (-2.3, 2.3):
        _trace('Resultados · guia de comparação', [(x-.55, .10, .82), (x+.55, .10, .82)],
               mats['muted'], 48, duration, draw=1.0, radius=.008)
    return _finish('results', duration, before)


def build_complements(duration=20):
    before = set(bpy.data.objects)
    mats = _materials('Complementos')
    _quiet_panel('Complementos · quantização', -4.3, 4.3, .65, 3.0,
                 mats, 0, 8)
    # Exact report count: five gains, four losses, three continuous selections.
    for i in range(12):
        color = 'cyan' if i < 5 else ('coral' if i < 9 else 'muted')
        marker = sphere(f'Complementos · escolha {i}',
                        (-3.75+i*.68, -.10, .82), .058, mats[color])
        _show(marker, .8+i*.15, 8)
    _quiet_panel('Complementos · histórico', -4.3, 4.3, .65, 3.0,
                 mats, 8, duration)
    # The paired-test statistic is depicted directly, avoiding a causal metaphor.
    for i in range(12):
        x = -3.75 + i*.68
        mat = mats['gold'] if i < 11 else mats['coral']
        glyph = box(f'Complementos · comparação histórica {i}',
                    (x, -.02, .83), (.17, .14, .22), mats['glass'], .02)
        _show(glyph, 8.7+i*.12, duration)
        _wire(f'Complementos · indicador histórico {i}',
              (x-.085, -.10, .72), (x+.085, .07, .94),
              mat, 8.7+i*.12, duration, radius=.006)
    return _finish('complements', duration, before)


def build_limits(duration=15):
    before = set(bpy.data.objects)
    mats = _materials('Limitações')
    for phase in range(3):
        start, end = phase*5, min(duration, (phase+1)*5)
        _quiet_panel(f'Limitações · cartão {phase}', -4.3, 4.3, .60, 3.0,
                     mats, start, end)
    # Descriptive differences: close illustrative profiles, without numerical axes.
    for index, mat in enumerate((mats['white'], mats['cyan'])):
        points = [(-4.1+i*.018, .02, .8+.22*math.sin(i*.10)+index*.045)
                  for i in range(65)]
        _trace(f'Limitações · proximidade {index}', points, mat,
               0, 5, draw=1, radius=.011)
    _show(sphere('Limitações · execução única', (-3.45, 0, 1.05), .13,
                 mats['gold']), 5, 10)
    for i in range(6):
        _show(sphere(f'Limitações · tarefa de seis passos {i}',
                     (2.5+i*.25, 0, 1.0), .04, mats['violet']),
              5+i*.10, 10)
    # Two observation windows share the same targets rather than independent data.
    _wire('Limitações · janela A', (-4.0, -.17, .65), (-2.8, .17, 1.50),
          mats['white'], 10, duration, radius=.009)
    _wire('Limitações · janela B', (-3.4, -.10, .65), (-2.2, .24, 1.50),
          mats['cyan'], 10.6, duration, radius=.009)
    for i in range(3):
        _show(sphere(f'Limitações · alvo compartilhado {i}',
                     (-3.3+i*.20, -.21, .9), .037, mats['gold']),
              11+i*.1, duration)
    return _finish('limits', duration, before)


def build_summary(duration=10):
    before = set(bpy.data.objects)
    mats = _materials('Síntese')
    groups = [(-2.3, 'cyan'), (2.3, 'violet')]
    for i, (x, color) in enumerate(groups):
        _quiet_panel(f'Síntese · grupo {i}', x-1.85, x+1.85, .65, 2.9,
                     mats, 0, duration)
        _trace(f'Síntese · identificação de grupo {i}',
               [(x-1.70, -.06, .66), (x+1.70, -.06, .66)],
               mats[color], .2, duration, draw=1.2, radius=.012)
        for j in range(2):
            marker = sphere(f'Síntese · tarefa {i}-{j}',
                            (x-.24+j*.48, -.08, .87), .058, mats[color])
            _show(marker, .5+j*.3, duration, pop=.5)
    return _finish('summary', duration, before)


BUILDERS = {
    'opening': build_opening,
    'objective': build_objective,
    'tasks': build_tasks,
    'evaluation': build_evaluation,
    'mae': build_mae,
    'results': build_results,
    'complements': build_complements,
    'limits': build_limits,
    'summary': build_summary,
}
