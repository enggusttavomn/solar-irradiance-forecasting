"""Sixty-second native3D explanation: model mechanisms, then common inputs.

The displayed state components, attention strengths and predictions are
didactic geometry, not tensors measured in the project's trained models.
Architectural ordering follows modelos_baselines_adicionais.py and the
project LSTM: sequential state; value/position attention; ProbSparse queries,
one separate encoder distillation and complete decoder cross-attention.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from common_v7 import (box, sphere, polyline, surface, emission, visible,
                       reveal, keys, label, camera_key, frame)

DURATION = 60
GHI = (.02, .10, .72, 1.0, .60, .05, .01, .18, .76, .68, .36, .02)
WEIGHTS = (.04, .05, .06, .12, .18, .09, .04, .17, .10, .05, .06, .04)
CUES = [
    [0, 4, 'comparar LSTM, Transformer e Informer. Como eles funcionam?'],
    [4, 8, 'Na LSTM, os valores entram em ordem.'],
    [8, 12, 'A memória muda a cada passo, por portas aprendidas.'],
    [12, 16, 'Elas regulam o que reter, acrescentar e transmitir.'],
    [16, 19, 'O estado final ajuda a prever todo o horizonte.'],
    [19, 23, 'No Transformer, cada posição reúne valor e ordem temporal.'],
    [23, 27, 'Consultas comparam representações com suas chaves.'],
    [27, 31, 'Os pesos calculados orientam a combinação dos valores.'],
    [31, 35, 'Essas representações seguem para a previsão do horizonte.'],
    [35, 39, 'Em sequências longas, o Informer detalha algumas consultas.'],
    [39, 43, 'A seleção usa uma estimativa de esparsidade.'],
    [43, 47, 'Em outra etapa, reduz a sequência interna do codificador.'],
    [47, 51, 'A atenção cruzada permanece completa.'],
    [51, 55, 'Agora, o mesmo histórico e a identificação da localidade entram nos três.'],
    [55, 60, 'Cada modelo produz diretamente um vetor para o mesmo horizonte.'],
]


def _shown(obj, start, end, pop=0):
    visible(obj, start, end)
    obj['v7_model_explainer'] = True
    if pop:
        size = tuple(obj.scale)
        keys(obj, 'scale', [(start, (.001,)*3), (start+pop, size)])
    return obj


def _intervals(obj, intervals):
    events = {0: True}
    for start, end in intervals:
        events[start] = False
        events[end] = True
    for second, hidden in sorted(events.items()):
        obj.hide_render = hidden
        obj.keyframe_insert('hide_render', frame=frame(second))


def _curve(name, points, mat, start, end, width=.025, draw=.45):
    obj = polyline('V7 '+name, points, mat, width)
    _shown(obj, start, end)
    if draw:
        reveal(obj, start, draw)
    return obj


def _arc(a, b, lift=.65, depth=.35, steps=26):
    a, b = Vector(a), Vector(b)
    points = []
    for i in range(steps+1):
        u = i/steps
        p = a.lerp(b, u)
        p.z += math.sin(math.pi*u)*lift
        p.y -= math.sin(math.pi*u)*depth
        points.append(tuple(p))
    return points


def _packet(name, points, mat, start, end, radius=.10):
    particle = _shown(sphere('V7 '+name, points[0], radius, mat), start, end, .10)
    keys(particle, 'location', [(start+(end-start)*i/(len(points)-1), point)
                                for i, point in enumerate(points)], True)
    return particle


def _text(name, body, location, mat, start, end, size=.38):
    return label('V7 '+name, body, location, size, mat, start, end)


def _body(name, location, dimensions, mat, start, end, pop=.25, bevel=.07):
    return _shown(box('V7 '+name, location, dimensions, mat, bevel), start, end, pop)


def _vector(name, position, mat, start, end, values=(.35, .75, .55), width=.48, scale=1):
    """Three visibly distinct components symbolise an internal vector."""
    root = bpy.data.objects.new('V7 '+name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = position
    objects = []
    gap = width/len(values)
    for i, value in enumerate(values):
        h = (.18+.56*value)*scale
        obj = _body(name+f' component{i}', ((i-(len(values)-1)/2)*gap, 0, h/2),
                    (gap*.77, .40*scale, h), mat, start, end, .20, min(.035, gap*.2))
        obj.parent = root
        objects.append(obj)
    return root, objects


def _future(name, origin, mat, start, end, values=(.30, .78, .62, .24), small=False):
    x, y, z = origin
    spacing = .47 if small else .61
    width = .29 if small else .37
    factor = .64 if small else 1.05
    objects = []
    for i, value in enumerate(values):
        h = .15+value*factor
        obj = _body(name+f' output{i}', (x+i*spacing, y, z+h/2),
                    (width, .47 if small else .65, h), mat, start, end, .32, .065)
        objects.append(obj)
    return objects


def _ring(name, center, mat, start, end, radius=.38, thickness=.06):
    x, y, z = center
    pts = [(x+radius*math.cos(i*math.tau/44), y,
            z+radius*1.18*math.sin(i*math.tau/44)) for i in range(45)]
    return _curve(name, pts, mat, start, end, thickness, .4)


def _shared_history(white):
    original = [(-6.7+i*.90, 0, 3.15+1.25*v) for i, v in enumerate(GHI)]
    compact = [(-6.8+i*.28, 0, 2.35+.90*v) for i, v in enumerate(GHI)]
    row = [(-5.5+i, .1, 3.65+.38*v) for i, v in enumerate(GHI)]
    curve = _curve('continuous historical curve', original, white, 0, 21.3, .035, .7)
    stages = [(0, original), (4, original), (5.8, compact), (18.95, compact), (20.55, row)]
    for i, point in enumerate(curve.data.splines[0].points):
        for second, positions in stages:
            point.co = (*positions[i], 1)
            point.keyframe_insert('co', frame=frame(second))
    dots = []
    for i, p in enumerate(original):
        dot = _shown(sphere('V7 historical sample '+str(i), p, .090, white), .3, 21.2, .22)
        keys(dot, 'location', [(second, positions[i]) for second, positions in stages])
        dots.append(dot)
    return compact, row, curve, dots


def _lstm(scene, m, compact):
    white, coral, muted = m['white'], m['coral'], m['muted']
    _text('LSTM name', 'LSTM', (-4.7, -.1, 6.10), coral, 4.15, 19, .64)
    _text('sequential values', 'GHI em ordem', (-5.35, -.4, 1.65), white, 5.6, 14.8, .36)
    _curve('LSTM state carry', [(-2.75, 0, 4.92), (2.15, 0, 4.92)], coral, 5.8, 17, .075, .8)
    _text('LSTM memory', 'Memória', (-.25, -.15, 5.65), white, 6.2, 16.8, .42)
    gate_x = (-1.75, -.1, 1.55)
    for j, (x, title) in enumerate(zip(gate_x, ('Reter', 'Acrescentar', 'Transmitir'))):
        _ring('LSTM learned gate ring '+str(j), (x, -.15, 3.65), coral, 6.1+j*.12, 16.9, .40, .075)
        blade = _body('LSTM continuous gate control '+str(j), (x, -.3, 3.65),
                      (.49, .35, .73), m['coral_dark'], 6.25+j*.12, 16.9, .25, .10)
        entries = []
        for i in range(13):
            opening = .30+.65*(.5+.5*math.sin(i*.72+j*1.1))
            entries.append((6.4+i*.68, (.36+opening*.64, 1, .50+opening*.50)))
        keys(blade, 'scale', entries)
        _text('LSTM gate label '+str(j), title, (x, -.4, 2.78), white, 8.0, 16.65, .32)
        _curve('LSTM gate to memory '+str(j),
               _arc((x, -.15, 4.10), (x, -.15, 4.90), .05, .05), muted,
               6.6+j*.15, 16.8, .018, .5)
    _text('LSTM multiply memory', '×', (-1.75, -.70, 4.93), white, 8, 15.9, .46)
    _text('LSTM add memory', '+', (-.1, -.70, 4.93), white, 8, 15.9, .47)
    for j in range(7):
        x = -2.45+j*.69
        state = _body('LSTM changing state '+str(j), (x, -.08, 5.02),
                      (.27, .34, .38), coral, 6.1+j*.05, 17, .2, .05)
        keys(state, 'scale', [(6.3+i*.68, (1, 1, .45+.8*abs(math.sin(i*.54+j*.65))))
                              for i in range(14)])
    _curve('LSTM input route', _arc((-3.45, 0, 2.75), (-1.75, -.17, 3.65), .25, .10),
           muted, 5.8, 15.8, .023, .6)
    for i in range(12):
        a = 5.9+i*.64
        points = _arc(compact[i], (-1.75, -.34, 3.65), .45, .30)
        points += _arc((-1.75, -.34, 3.65), (-.1, -.33, 4.92), .12, .1)[1:]
        _packet('LSTM ordered input '+str(i), points, white, a, a+1.40, .10)
    # Expose the transmitted hidden state as well as memory retention/update.
    # This is still internal state flow, not recursive forecast feedback.
    transmitted = (_arc((1.8, -.05, 4.92), (1.55, -.35, 3.65), .08, .20)
                   + _arc((1.55, -.35, 3.65), (2.7, -.05, 2.95), .0, .10)[1:])
    _curve('LSTM transmitted internal state', transmitted, muted, 8.6, 16.8, .022, .55)
    for j in range(4):
        a = 9.2+j*1.55
        _packet('LSTM transmitted state packet '+str(j), transmitted, coral, a, a+1.1, .10)
    _curve('LSTM final state route', _arc((1.8, 0, 4.92), (3.25, 0, 3.15), .0, .05),
           coral, 15.6, 19, .045, .7)
    _vector('LSTM final hidden state representation', (1.45, 0, 4.55), coral,
            16.75, 19, (.48, .72, .55), .90, 1.2)
    _text('LSTM final hidden state label', 'Estado final', (1.45, -.2, 5.65), white,
           16.9, 19, .36)
    # Locality is concatenated to the final state in the project LSTM head.
    idroot, _ = _vector('LSTM locality embedding', (2.8, -.15, 5.50), white, 16.0, 18.4,
                       (.32, .75, .43), .50, .7)
    keys(idroot, 'location', [(16.0, (2.8, -.15, 5.50)), (17.0, (3.25, -.15, 3.25))])
    _text('LSTM locality label', 'ID', (3.55, -.2, 5.75), white, 16.0, 17.3, .34)
    _future('LSTM direct horizon', (3.45, -.05, 2.45), coral, 17, 19)
    _text('LSTM direct future label', 'Vetor futuro', (4.4, -.2, 1.75), white, 17.2, 19, .39)


def _transformer(scene, m, row):
    white, cyan = m['white'], m['cyan']
    _text('Transformer name', 'Transformer', (-3.9, -.05, 6.65), cyan, 19.05, 35, .60)
    for i, value in enumerate(GHI):
        p = (-5.5+i, .10, 3.65)
        _, bars = _vector('Transformer represented position '+str(i), p, cyan, 20.4+i*.035, 27.1,
                          (.23+.55*value, .72-.30*value, .38+.30*math.sin(i*.7)**2), .56)
        marker = _body('Transformer temporal position component '+str(i),
                       (p[0], -.27, 3.25), (.43, .13, .12), white, 21.05+i*.03, 23.2, .18, .025)
        keys(marker, 'location', [(21.1+i*.03, (p[0], -.27, 3.25)),
                                  (22.25+i*.025, (p[0], -.27, 3.62))])
    _text('Transformer value and temporal position', 'Valor + posição', (0, -.2, 5.17), white,
           20.8, 23.1, .43)
    query = (-5.2, -.2, 5.20)
    q, _ = _vector('Transformer query', query, cyan, 23, 27.1, (.8, .45, .67), .65)
    _text('Transformer query label', 'Consulta', (-5.15, -.25, 5.95), white, 23.15, 27, .36)
    _text('Transformer key label', 'Chaves', (2.2, -.25, 5.27), white, 23.3, 27, .36)
    for i in range(12):
        endpoint = (-5.5+i, -.03, 4.18)
        pts = _arc((query[0], query[1], query[2]+.4), endpoint, .26, .12)
        _curve('Transformer query key comparison '+str(i), pts,
               m['cyan_soft'] if WEIGHTS[i] < .1 else cyan, 23.35+i*.055, 27.10,
               .009+.050*WEIGHTS[i], .60)
        _packet('Transformer similarity comparison '+str(i), pts, cyan,
                24.0+i*.055, 24.85+i*.055, .045+.07*WEIGHTS[i])
    # All twelve weighted contributions are shown, in three batches of four.
    # Batching prevents a dense simultaneous web from hiding the operation.
    target = (4.9, -.15, 4.6)
    merged, merged_bars = _vector('Transformer weighted updated representation', target, cyan,
                                  27.2, 31.35, (.42, .68, .55), .90, 1.5)
    _text('Transformer weighted combination label', 'Combinar valores', (3.9, -.2, 5.95), white,
           27.15, 31.2, .40)
    for i, value in enumerate(GHI):
        x = -5.5+i
        _vector('Transformer V value '+str(i), (x, .05, 2.85), m['cyan_dark'], 27, 31.3,
                (.21+.56*value, .67-.35*value, .33+.25*math.sin(i*.7)**2), .48, .80)
        height = .10+WEIGHTS[i]*3.4
        _body('Transformer normalized influence '+str(i), (x, -.40, 2.10+height/2),
              (.18, .24, height), cyan, 27, 31.3, .25, .03)
        batch = i//4
        start = 27.45+batch*.92
        pts = _arc((x, -.15, 3.1), (target[0], target[1], target[2]+.3), .30, .20)
        _curve('Transformer weighted contribution '+str(i), pts, m['cyan_soft'],
               start, start+.88, .012, .20)
        _packet('Transformer weighted value '+str(i), pts, cyan,
                start+.06, start+.83, .055+.42*WEIGHTS[i])
    _text('Transformer weights label', 'Pesos', (-3.3, -.3, 1.58), white, 27.3, 31.1, .36)
    for j, bar in enumerate(merged_bars):
        keys(bar, 'scale', [(27.25, (1, 1, .35)), (28.35, (1, 1, .55)),
                            (29.25, (1, 1, .78)), (30.35, (1, 1, 1))])
    # The learned representations feed a direct regression horizon.
    for j in range(3):
        _vector('Transformer contextual representation '+str(j), (-3.8+j*1.1, .0, 3.4),
                cyan, 31.2+j*.08, 35, (.34+j*.13, .65-j*.10, .48), .67, 1.2)
    _curve('Transformer representation to forecast', _arc((-1.2, 0, 3.85), (2.65, 0, 3.2), .70, .28),
           cyan, 31.65, 35, .035, .6)
    _packet('Transformer encoded information', _arc((-2.5, 0, 3.85), (2.65, 0, 3.2), .70, .28),
            white, 32.0, 33.0, .12)
    _future('Transformer direct horizon', (2.95, -.05, 2.6), cyan, 32.8, 35,
            (.31, .76, .65, .23))
    _text('Transformer vector future label', 'Vetor futuro', (3.9, -.2, 1.8), white, 33.0, 35, .40)


def _informer(scene, m):
    white, violet, muted = m['white'], m['violet'], m['muted']
    _text('Informer name', 'Informer', (-4.55, -.05, 6.15), violet, 35.05, 51, .64)
    _text('Informer long sequence', 'Sequências longas', (2.4, -.1, 6.15), white, 35.3, 39.0, .36)
    for i, value in enumerate(GHI):
        _vector('Informer historical representation '+str(i), (-5.5+i, .1, 3.85),
                violet if i in (1, 7) else m['violet_dark'], 35.35+i*.035, 46.9,
                (.23+.55*value, .72-.3*value, .32+.26*math.sin(i*.7)**2), .55)
    # Low-amplitude sample indices are deliberately chosen for the schematic
    # queries, so the viewer cannot infer that ProbSparse selects largest GHI.
    selected = (1, 7)
    for j, index in enumerate(selected):
        query = (-5.5+index, -.15, 5.10)
        _vector('Informer selected query '+str(j), query, violet, 36.2+j*.22, 42.9,
                (.7, .4, .64), .63)
        _curve('Informer query lifting '+str(j),
               [(-5.5+index, .05, 4.45), query], muted, 36.25+j*.22, 42.8, .018, .45)
        for k, key_index in enumerate((0, 3, 6, 10)):
            pts = _arc((query[0], -.1, 5.5), (-5.5+key_index, .05, 4.35), .13, .12)
            _curve(f'Informer sampled estimate {j}-{k}', pts, m['violet_soft'],
                   36.6+j*.20, 38.9, .012, .5)
        start = 39.0+j*1.6
        for key_index in range(12):
            pts = _arc((query[0], -.1, 5.5), (-5.5+key_index, .05, 4.35), .15, .12)
            _curve(f'Informer detailed selected query {j}-{key_index}', pts, m['violet_soft'],
                   start, min(42.9, start+1.65), .012, .40)
            if key_index%3 == 0:
                _packet(f'Informer selected query update {j}-{key_index}', pts, violet,
                        start+.24, start+1.3, .065)
    _text('Informer query selection', 'Consultas selecionadas', (.0, -.25, 6.00), white, 39.0, 42.9, .39)
    # A distinct operation reduces internal representation length. The input
    # timestamps are not discarded, and this is not the query selection step.
    _text('Informer separate encoder reduction', 'Convolução + redução', (.0, -.25, 5.80), white, 43.05, 46.85, .41)
    encoder_positions = []
    for j in range(6):
        destination = (-4.75+j*1.9, .05, 2.35)
        root, _ = _vector('Informer distilled representation '+str(j), destination, violet,
                          43.4+j*.10, 51, (.35+.25*math.sin(j*.7)**2, .67-j*.035, .48), .80, 1.12)
        keys(root, 'location', [(46.65, destination), (47.15, (destination[0], .05, 4.45))])
        encoder_positions.append((destination[0], .05, 4.80))
        for k in range(3):
            index = min(11, max(0, j*2+k-1))
            source = (-5.5+index, .05, 3.92)
            pts = _arc(source, (destination[0], .05, 2.85), .0, .15)
            _curve(f'Informer convolution contribution {j}-{k}', pts, m['violet_soft'],
                   43.3+j*.08, 46.75, .014, .45)
            _packet(f'Informer representation reduction {j}-{k}', pts, violet,
                    43.8+j*.15+k*.08, 44.7+j*.15+k*.08, .065)
    # Complete cross-attention: six encoder keys connect to all four visible
    # future decoder queries. Highlight one query at a time for legibility.
    _text('Informer complete cross attention', 'Atenção cruzada completa', (.0, -.25, 6.0), white, 47.2, 51, .42)
    decoder_positions = [(-3.15+j*2.1, .05, 2.45) for j in range(4)]
    for j, destination in enumerate(decoder_positions):
        _vector('Informer future decoder query '+str(j), destination, violet, 47.15, 51,
                (.36+j*.10, .66-j*.05, .44), .72)
        for i, source in enumerate(encoder_positions):
            pts = _arc(source, (destination[0], .05, destination[2]+.65), .05, .12)
            _curve(f'Informer full cross-attention {j}-{i}', pts, m['violet_soft'],
                   47.3+j*.20, 51, .010, .35)
            if i in (j%6, (j+3)%6):
                a = 47.65+j*.54
                _packet(f'Informer complete cross-attention update {j}-{i}', pts, violet,
                        a, a+.68, .062)
    _text('Informer forecast positions label', 'Posições futuras', (.0, -.2, 1.57), white, 47.65, 51, .36)


def _comparison(scene, m):
    white = m['white']
    _text('comparison same information', 'Mesmo histórico + ID', (-4.5, -.05, 6.25), white, 51.05, 60, .47)
    points = [(-7.2+i*.28, .05, 3.65+.82*v) for i, v in enumerate(GHI)]
    _curve('comparison exact same GHI history', points, white, 51.05, 60, .034, .65)
    for i, p in enumerate(points):
        _shown(sphere('V7 comparison common sample '+str(i), p, .070, white), 51.20+i*.025, 60, .10)
    _text('comparison historical data label', 'GHI passado', (-5.5, -.15, 3.05), white, 51.6, 60, .32)
    idroot, _ = _vector('comparison exact same locality embedding', (-5.5, 0, 1.95), white,
                        51.5, 60, (.32, .75, .43), .70, .86)
    _text('comparison locality identifier label', 'ID da localidade', (-5.5, -.15, 1.43), white, 51.8, 60, .32)
    junction = (-2.6, -.1, 3.67)
    _curve('comparison GHI to common junction', [points[-1], junction], m['muted'], 52, 60, .024, .45)
    _curve('comparison ID to common junction', _arc((-5.5, 0, 2.6), junction, .1, .2),
           m['muted'], 52, 60, .024, .50)
    _text('comparison common horizon label', 'Mesmo horizonte', (4.8, -.1, 6.25), white, 55.0, 60, .43)
    rows = [('LSTM', 5.0, m['coral'], (.30, .76, .63, .23)),
            ('Transformer', 3.45, m['cyan'], (.32, .78, .61, .24)),
            ('Informer', 1.90, m['violet'], (.29, .74, .65, .25))]
    for j, (name, z, mat, outputs) in enumerate(rows):
        center = (.7, 0, z)
        _text('comparison model '+name, name, (.65, -.1, z+.74), mat, 51.4+j*.10, 60, .39)
        # Small recognisable mechanisms echo the preceding close-up, rather
        # than turning the networks into three unexplained closed boxes.
        if name == 'LSTM':
            _curve('comparison LSTM memory', [(-.2, 0, z+.25), (1.65, 0, z+.25)], mat, 51.6, 60, .042, .5)
            for i in range(3):
                _ring('comparison LSTM gate '+str(i), (.05+i*.58, 0, z-.08), mat,
                      51.65, 60, .18, .035)
        elif name == 'Transformer':
            for i in range(4):
                _vector('comparison Transformer token '+str(i), (-.12+i*.55, 0, z-.24),
                        mat, 51.7, 60, (.4, .7, .5), .31, .52)
            for i in range(3):
                _curve('comparison Transformer attention '+str(i),
                       _arc((-.12, 0, z+.12), (.43+i*.55, 0, z+.12), .25, .1),
                       mat, 51.8, 60, .016, .45)
        else:
            for i in range(6):
                _body('comparison Informer representation '+str(i), (-.25+i*.36, 0, z-.05),
                      (.22, .30, .30), mat, 51.8, 60, .18, .05)
            _shown(sphere('V7 comparison selected Informer query', (.47, 0, z+.44), .10, mat), 51.9, 60, .15)
        route = _arc(junction, (-.25, -.1, z), .05, .14)
        _curve('comparison common input route '+name, route, m['muted'], 52.4, 60, .020, .5)
        _packet('comparison synchronized GHI '+name, route, white, 53.0, 54.4, .10)
        _packet('comparison synchronized ID '+name, route, white, 53.25, 54.65, .065)
        exit_route = _arc((1.8, 0, z), (3.7, 0, z), .10, .10)
        _curve('comparison direct forecast route '+name, exit_route, mat, 54.8, 60, .032, .55)
        _packet('comparison simultaneous forecast '+name, exit_route, mat, 55.0, 55.8, .11)
        _future('comparison common format '+name, (4.0, -.05, z-.37), mat, 55.7, 60, outputs, True)


def build(scene):
    before = set(bpy.data.objects)
    palette = {'coral': (.88, .29, .20, 1), 'coral_dark': (.56, .16, .11, 1),
               'cyan': (.10, .58, .73, 1), 'cyan_dark': (.075, .30, .38, 1),
               'violet': (.49, .29, .75, 1), 'violet_dark': (.24, .14, .40, 1)}
    m = {name: surface('V7 matte '+name, color, .025, .58) for name, color in palette.items()}
    m['white'] = emission('V7 clean explanatory white', (.89, .94, .99, 1), 1.0)
    m['muted'] = emission('V7 subtle structural connection', (.20, .28, .34, 1), .65)
    m['cyan_soft'] = emission('V7 weighted cyan connection', (.08, .35, .43, 1), .65)
    m['violet_soft'] = emission('V7 selected violet connection', (.28, .16, .43, 1), .70)
    # Camera shifts are small and continuous; models occupy the screen one
    # at a time before the final shared-input comparison.
    for second, loc, target, scale in [
        (0, (1.1, -26, 7.6), (0, 0, 3.6), 16.6),
        (4, (1.4, -26, 7.5), (0, 0, 3.6), 16.6),
        (8.5, (1.0, -25, 7.0), (0, 0, 3.65), 16.3),
        (15, (-.7, -25.5, 7.1), (.1, 0, 3.65), 16.3),
        (19, (-1.3, -26, 7.4), (0, 0, 3.70), 16.6),
        (25, (-.3, -25.5, 7.0), (0, 0, 3.75), 16.5),
        (31, (1.0, -25.5, 7.0), (.1, 0, 3.7), 16.6),
        (35, (1.0, -26, 7.5), (0, 0, 3.75), 16.8),
        (43, (-.6, -25.5, 7.1), (0, 0, 3.7), 16.8),
        (47, (-1.0, -25.6, 7.0), (0, 0, 3.8), 16.6),
        (51, (.3, -26, 7.4), (0, 0, 3.65), 17.2),
        (60, (-.5, -26, 7.2), (0, 0, 3.65), 17.2),
    ]:
        camera_key(scene, second, loc, target, scale)
    for owner in (scene.camera, scene.camera.data):
        if owner.animation_data and owner.animation_data.action:
            for curve in owner.animation_data.action.fcurves:
                for key in curve.keyframe_points:
                    key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
    _text('goal historical forecasting', 'Do histórico à previsão', (0, -.1, 6.0), m['white'], 0, 4, .55)
    compact, row, curve, dots = _shared_history(m['white'])
    for j in range(9):
        x = 3.6+j*.34
        a = (x, 0, 3.2+.55*math.sin((x-3.6)*2.5))
        b = (x+.18, 0, 3.2+.55*math.sin((x+.18-3.6)*2.5))
        _curve('goal future dashed continuation '+str(j), [a, b], m['cyan_soft'], .8, 4, .026, .2)
    _text('goal historical label', 'GHI passado', (-3.0, -.15, 2.35), m['white'], .5, 4, .36)
    _text('goal future label', 'Futuro', (5.0, -.15, 2.35), m['white'], .8, 4, .36)
    _lstm(scene, m, compact)
    _transformer(scene, m, row)
    _informer(scene, m)
    _comparison(scene, m)
    scene.frame_set(1)
    return {
        'version': 7, 'duration': DURATION,
        'title': 'Mecanismos das redes antes da comparação de entradas',
        'qa_times': [1.5, 6.5, 10.5, 14.0, 17.8, 21.7, 25.0, 28.8, 33.5,
                     37.5, 40.0, 44.8, 48.8, 53.7, 57.3],
        'cues': CUES,
        'phases': [[0, 4, 'goal'], [4, 19, 'LSTM sequential memory and continuous gates'],
                   [19, 35, 'Transformer value-position, queries-keys, weighted values'],
                   [35, 43, 'Informer selected queries in long contexts'],
                   [43, 47, 'separate encoder representation distillation'],
                   [47, 51, 'complete cross-attention'], [51, 60, 'identical history and locality inputs']],
        'visible_history_samples': 12, 'history_values_schematic': list(GHI),
        'future_vector_components_schematic': 4,
        'all_models_output_direct_horizon': True, 'recursive_forecast_feedback': False,
        'LSTM_locality_join': 'final recurrent state concatenated with locality embedding before the output head',
        'Transformer_input': 'GHI projection plus position representation plus locality projection',
        'Informer_query_selection': 'illustrative estimated sparsity, not largest GHI amplitudes',
        'Informer_selected_visible_indices': [1, 7],
        'Informer_short_context_note': 'The local implementation can select every query on short contexts; the sparse animation depicts a long context schematically.',
        'encoder_distillation_stages': 1, 'encoder_representation_count_illustrative': [12, 6],
        'decoder_cross_attention_complete': True, 'illustrative_cross_attention_edges': 24,
        'same_history_and_locality_in_final_comparison': True,
        'same_output_format_does_not_mean_identical_predicted_values': True,
        'weights_states_and_predictions': 'didactic geometry, not measurements extracted from the fitted networks',
        'performance_or_speed_claims': False, 'error_rankings': False,
        'object_count': len(set(bpy.data.objects)-before),
        'references': [
            {'kind': 'visual', 'url': 'https://www.3blue1brown.com/lessons/attention/'},
            {'kind': 'paper', 'url': 'https://arxiv.org/abs/1706.03762'},
            {'kind': 'paper', 'url': 'https://arxiv.org/abs/2012.07436'},
            {'kind': 'paper', 'url': 'https://people.idsia.ch/~juergen/lstm1997-2024head.pdf'},
            {'kind': 'implementation', 'path': 'codigo_fonte/modelos/modelos_baselines_adicionais.py'},
            {'kind': 'implementation', 'path': 'codigo_fonte/modelos/recorrentes/modelos_neurais_globais.py'},
        ],
    }
