"""Geometria animada de arquiteturas e quantização para o vídeo da EA019.

As funções apenas acrescentam objetos à cena atual. Câmera, iluminação,
piso, renderização e textos de tela pertencem ao montador do vídeo.
Os esquemas são didáticos; não são gráficos de resultados experimentais.
"""

import math

import bpy
from mathutils import Vector

from blender_pilot import (
    box, emission, polyline, reveal, sphere, surface, visible, wire_box,
)


CORAL = (1.0, .29, .24, 1.0)
CYAN = (.10, .75, .90, 1.0)
VIOLET = (.59, .29, 1.0, 1.0)
WHITE = (.88, .94, 1.0, 1.0)
GOLD = (1.0, .63, .20, 1.0)


def _frame(seconds):
    return round(float(seconds) * 30) + 1


def _strength(material, keys):
    """Animar apenas a emissão, sem alterar a visibilidade da estrutura."""
    node = material.node_tree.nodes.get('Emission')
    if node is None:
        node = next(n for n in material.node_tree.nodes if n.type == 'EMISSION')
    socket = node.inputs['Strength']
    for seconds, value in keys:
        socket.default_value = value
        socket.keyframe_insert('default_value', frame=_frame(seconds))


def _focus(material, start, end, duration, peak=1.8):
    keys = [(0, .13), (max(0, start-.35), .13),
            (start+.7, peak), (max(start+.8, end-.8), peak),
            (min(duration, end+.4), .13), (duration, .13)]
    _strength(material, keys)


def _motion(obj, keys):
    for seconds, position in keys:
        obj.location = position
        obj.keyframe_insert('location', frame=_frame(seconds))


def _show(obj, duration, start=0):
    visible(obj, start, duration+.05)
    return obj


def _wire_cell(name, center, dimensions, material, body, duration):
    center = Vector(center)
    half = Vector(dimensions) * .5
    cell = _show(box(name, center, dimensions, body, .035), duration)
    edges = wire_box(name+' contorno', center-half, center+half, material, .009)
    for edge in edges:
        _show(edge, duration)
    return cell, edges


def _arrow(name, start, end, material, duration, radius=.009):
    """Seta espacial simples; a ponta não representa realimentação."""
    start, end = Vector(start), Vector(end)
    direction = (end-start).normalized()
    side = direction.cross(Vector((0, 1, 0)))
    if side.length < .001:
        side = direction.cross(Vector((1, 0, 0)))
    side.normalize()
    stem = _show(polyline(name, [start, end], material, radius), duration)
    for sign in (-1, 1):
        _show(polyline(name+f' ponta {sign}',
                       [end-direction*.11+side*(sign*.055), end],
                       material, radius), duration)
    return stem


def _arc(a, b, height=.65, depth=.12, count=28):
    a, b = Vector(a), Vector(b)
    result = []
    for i in range(count+1):
        u = i/count
        point = a.lerp(b, u)
        point.z += math.sin(math.pi*u)*height
        point.y += math.sin(math.pi*u)*depth
        result.append(tuple(point))
    return result


def _new_names(before):
    return [obj.name for obj in bpy.data.objects if obj.name not in before]


def build_models(duration=55):
    """Criar LSTM à esquerda, Transformer ao centro e Informer à direita.

    Fases proporcionais aos 55 s de referência: 0–17 / 17–34 / 34–55.
    Todos os grupos permanecem presentes; a emissão e os pulsos dirigem o foco.
    Retorna metadados das fases e nomes de objetos, sem gravar arquivos.
    """
    duration = float(duration)
    before = {obj.name for obj in bpy.data.objects}
    time_scale = duration/55.0
    t = lambda seconds: seconds*time_scale
    base = surface('Arquiteturas · bases escuras', (.010, .023, .034, 1), .35, .3)
    glass = surface('Arquiteturas · volumes escuros', (.030, .066, .082, 1), .15, .24, .24)
    coral = emission('LSTM · foco coral', CORAL, .13)
    cyan = emission('Transformer · foco ciano', CYAN, .13)
    violet = emission('Informer · foco violeta', VIOLET, .13)
    _focus(coral, t(0), t(17), duration)
    _focus(cyan, t(17), t(34), duration)
    _focus(violet, t(34), duration, duration)
    for name, x, color in [('LSTM', -3.10, coral), ('Transformer', 0, cyan), ('Informer', 3.10, violet)]:
        _show(box(name+' plataforma', (x, .12, .28), (2.72, 1.72, .13), base, .055), duration)
        _show(polyline(name+' linha da plataforma',
                       [(x-1.23, -.72, .355), (x+1.23, -.72, .355)], color, .011), duration)

    # LSTM: percurso sequencial, memória transportada e vetor futuro direto.
    cell_centers = [(-4.10, -.10, 1.25), (-3.45, -.10, 1.25), (-2.80, -.10, 1.25)]
    for i, center in enumerate(cell_centers):
        _wire_cell(f'LSTM célula {i+1}', center, (.44, .48, .85), coral, glass, duration)
    memory_points = [(-4.34, -.10, 2.08), (-2.58, -.10, 2.08)]
    _show(polyline('LSTM estado de memória', memory_points, coral, .016), duration)
    for i, (x, y, z) in enumerate(cell_centers):
        _arrow(f'LSTM atualização da memória {i+1}', (x, y, 1.71), (x, y, 2.08), coral, duration)
        if i < len(cell_centers)-1:
            _arrow(f'LSTM fluxo sequencial {i+1}', (x+.23, y, 1.25),
                   (cell_centers[i+1][0]-.23, y, 1.25), coral, duration)
    _arrow('LSTM entrada', (-4.43, -.10, 1.25), (-4.34, -.10, 1.25), coral, duration)
    pulse_mat = emission('LSTM · informação em movimento', CORAL, 2.8)
    pulse = sphere('LSTM pulso de memória', (-4.34, -.10, 2.08), .072, pulse_mat)
    visible(pulse, t(.8), t(15.8))
    _motion(pulse, [(t(.8), (-4.34, -.10, 2.08)),
                    (t(4.7), (-4.10, -.10, 2.08)),
                    (t(8.4), (-3.45, -.10, 2.08)),
                    (t(12.1), (-2.80, -.10, 2.08)),
                    (t(15.6), (-2.58, -.10, 2.08))])
    # Todas as saídas saem do último estado: não há previsão realimentada.
    for j, z in enumerate((.91, 1.25, 1.59)):
        tip = (-2.10, -.10, z)
        out = _arrow(f'LSTM saída direta {j+1}', (-2.56, -.10, 1.25), tip, coral, duration)
        reveal(out, t(12.5), t(1.2))
        _wire_cell(f'LSTM vetor futuro {j+1}', (-1.98, -.10, z), (.21, .32, .22), coral, glass, duration)
        dot = sphere(f'LSTM componente futura {j+1}', tip, .045, pulse_mat)
        visible(dot, t(13.7), t(16.5))

    # Transformer: posições e combinações de atenção, não um fluxo recorrente.
    nodes = [(-1.04, -.25, 1.12), (-.52, .15, 1.12), (0, -.10, 1.12),
             (.52, .20, 1.12), (1.04, -.20, 1.12)]
    for i, pos in enumerate(nodes):
        _wire_cell(f'Transformer posição {i+1}', pos, (.25, .35, .74), cyan, glass, duration)
        x, y, _ = pos
        _show(box(f'Transformer marcador de ordem {i+1}', (x, -.52, .51),
                  (.085, .15, .13+(i*.035)), cyan, .01), duration)
        _show(polyline(f'Transformer projeção posicional {i+1}',
                       [(x, -.52, .63+i*.015), (x, y, .74)], cyan, .006), duration)
    for i in range(len(nodes)):
        for j in range(i+1, len(nodes)):
            a = (nodes[i][0], nodes[i][1], 1.51)
            b = (nodes[j][0], nodes[j][1], 1.51)
            weight = .45+.13*((i*3+j*2) % 5)
            mat = emission(f'Transformer atenção {i+1}–{j+1}', CYAN, .08)
            edge = _show(polyline(f'Transformer relação {i+1}–{j+1}',
                                 _arc(a, b, .37+.22*(j-i), .10+.03*i), mat,
                                 .006+weight*.005), duration)
            _strength(mat, [(0, .06), (t(17), .06), (t(19+i*.45), weight*1.7),
                            (t(24+j*.6), weight*.7), (t(29+i*.3), weight*1.9),
                            (t(34), .08), (duration, .08)])
    query_mat = emission('Transformer · posição em foco', CYAN, 2.5)
    query = sphere('Transformer consulta móvel', nodes[0], .065, query_mat)
    visible(query, t(18), t(33.8))
    _motion(query, [(t(18+i*3.1), (p[0], p[1], 1.63)) for i, p in enumerate(nodes)] +
                   [(t(33.7), (nodes[-1][0], nodes[-1][1], 1.63))])

    # Informer: consultas selecionadas e destilação temporal entre camadas.
    top = [(2.03+i*.535, .0, 2.36) for i in range(5)]
    middle = [(2.38+i*.72, .15, 1.48) for i in range(3)]
    bottom = [(2.74+i*.74, .30, .72) for i in range(2)]
    for row_name, row, dim in [('consultas', top, (.30, .38, .38)),
                               ('destilação 1', middle, (.38, .38, .36)),
                               ('destilação 2', bottom, (.42, .38, .32))]:
        for i, center in enumerate(row):
            _wire_cell(f'Informer {row_name} {i+1}', center, dim, violet, glass, duration)
    selected_mat = emission('Informer · consultas selecionadas', VIOLET, 2.6)
    selected = (0, 3)
    for i in selected:
        focus = sphere(f'Informer consulta selecionada {i+1}',
                       (top[i][0], top[i][1]-.02, 2.72), .080, selected_mat)
        visible(focus, t(35.5+i*.25), t(44.5))
        for j in (0, 2, 4):
            if i == j:
                continue
            detailed = polyline(f'Informer cálculo detalhado consulta {i+1} chave {j+1}',
                                _arc((top[i][0], .02, 2.61),
                                     (top[j][0], .35, 2.61), .23+.08*abs(i-j), .05),
                                selected_mat, .009)
            visible(detailed, t(36.0), t(44.5))
            reveal(detailed, t(36.0), t(2.5))
    for level, (row_a, row_b) in enumerate(((top, middle), (middle, bottom))):
        for i, a in enumerate(row_a):
            b = row_b[min(len(row_b)-1, i*len(row_b)//len(row_a))]
            a = (a[0], a[1], a[2]-.21)
            b = (b[0], b[1], b[2]+.20)
            line = _arrow(f'Informer redução camada {level+1} ligação {i+1}', a, b, violet, duration, .007)
            reveal(line, t(43+level*4), t(3.0))
    distill = sphere('Informer informação entre camadas', top[2], .073, selected_mat)
    visible(distill, t(43), t(54.4))
    _motion(distill, [(t(43), (top[2][0], top[2][1], 2.36)),
                      (t(47), middle[1]), (t(51.5), bottom[0]),
                      (t(54.3), bottom[0])])
    return {
        'object_names': _new_names(before),
        'phases': [
            {'start': t(0), 'end': t(17), 'label': 'LSTM · memória temporal'},
            {'start': t(17), 'end': t(34), 'label': 'Transformer · atenção entre posições'},
            {'start': t(34), 'end': duration, 'label': 'Informer · ProbSparse e destilação'},
        ],
        'required_note': 'Esquema simplificado. Atenção cruzada do Informer permanece completa. Custo computacional não medido.',
    }


def _quantizer_points(levels, x_min=-3.85, x_max=3.85, z_zero=.67, height=2.10, y=-.06):
    """Transferência rint(clip(u, 0, 1)*(N-1))/(N-1), desenhada por patamares."""
    def x(u):
        return x_min+(u+.15)/1.30*(x_max-x_min)
    points = [(x(-.15), y, z_zero)]
    for k in range(levels-1):
        threshold = (k+.5)/(levels-1)
        points.append((x(threshold), y, z_zero+height*k/(levels-1)))
        points.append((x(threshold), y, z_zero+height*(k+1)/(levels-1)))
    points.append((x(1.15), y, z_zero+height))
    return points


def build_quantization(duration=35):
    """Curva de transferência de amplitude: contínua, Q64, Q128 e Q256.

    Os degraus usam os números reais de níveis. As linhas horizontais tênues
    são guias de leitura, não uma contagem de níveis do quantizador.
    Não há redução do número de instantes nem quantização de pesos.
    """
    duration = float(duration)
    before = {obj.name for obj in bpy.data.objects}
    t = lambda seconds: seconds*duration/35.0
    axis = emission('Quantização · eixos', (.20, .32, .39, 1), .75)
    guide = emission('Quantização · guias de amplitude', (.055, .105, .13, 1), .55)
    continuous = emission('Quantização · entrada contínua', WHITE, 1.2)
    quantized = emission('Quantização · entrada reconstruída', CYAN, 1.8)
    sample_mat = emission('Quantização · valor de entrada', GOLD, 2.1)
    _show(polyline('Quantização eixo amplitude de entrada', [(-4.12, .12, .48), (4.12, .12, .48)], axis, .008), duration)
    _show(polyline('Quantização eixo amplitude representada', [(-4.12, .12, .48), (-4.12, .12, 3.27)], axis, .008), duration)
    for k in range(9):
        z = .67+2.10*k/8
        _show(polyline(f'Quantização guia de leitura {k}', [(-4.02, .16, z), (4.02, .16, z)], guide, .003), duration)
    # O controle contínuo não aplica clipping: a diagonal se estende aos extremos.
    line = _show(polyline('Quantização controle contínuo sem clipping',
                         [(-3.85, .03, .355), (3.85, .03, 3.085)], continuous, .013), duration)
    reveal(line, 0, t(3.5))
    _strength(continuous, [(0, 1.3), (t(4.5), 1.3), (t(6), .48), (duration, .48)])
    for levels, start, end in [(64, 5, 15), (128, 15, 25), (256, 25, 35)]:
        curve = polyline(f'Quantização Q{levels} · níveis reais',
                         _quantizer_points(levels), quantized, .015)
        visible(curve, t(start), t(end))
        reveal(curve, t(start), t(.85))
        # Casos de entrada são revelados individualmente. Não interpolar uma
        # saída entre dois níveis, o que criaria valores que o quantizador não usa.
        for index, u in enumerate((-.08, .245, .735, 1.08)):
            value = round(max(0, min(1, u))*(levels-1))/(levels-1)
            x = -3.85+(u+.15)/1.30*7.70
            show_start = start+1.0+index*2.1
            show_end = min(end-.15, show_start+1.9)
            input_point = sphere(f'Quantização Q{levels} · entrada caso {index+1}',
                                 (x, -.035, .67+2.10*u), .046, sample_mat)
            output_point = sphere(f'Quantização Q{levels} · saída caso {index+1}',
                                  (x, -.070, .67+2.10*value), .052, quantized)
            visible(input_point, t(show_start), t(show_end))
            visible(output_point, t(show_start), t(show_end))
            difference = polyline(f'Quantização Q{levels} · diferença caso {index+1}',
                                  [(x, -.035, .67+2.10*u), (x, -.070, .67+2.10*value)],
                                  sample_mat, .006)
            visible(difference, t(show_start), t(show_end))
    # Saturação é mostrada por dois pequenos limites; só as variantes quantizadas
    # usam esses patamares, enquanto a diagonal branca segue além do intervalo.
    boundary = emission('Quantização · limites de clipping', GOLD, .9)
    x0 = -3.85+.15/1.30*7.70
    x1 = -3.85+1.15/1.30*7.70
    for name, x, z in [('inferior', x0, .67), ('superior', x1, 2.77)]:
        segment = polyline('Quantização limite '+name,
                           [(x, .06, z-.10), (x, .06, z+.10)], boundary, .013)
        visible(segment, t(5), duration+.05)
    return {
        'object_names': _new_names(before),
        'phases': [
            {'start': 0, 'end': t(5), 'label': 'Controle contínuo'},
            {'start': t(5), 'end': t(15), 'label': 'Q64'},
            {'start': t(15), 'end': t(25), 'label': 'Q128'},
            {'start': t(25), 'end': duration, 'label': 'Q256'},
        ],
        'axis_labels': {'x': 'Amplitude de entrada normalizada', 'z': 'Amplitude representada'},
        'required_note': 'Clipping + arredondamento somente na entrada de GHI. Reconstrução em float32; pesos e saídas contínuos.',
        'visual_note': 'Guias horizontais são referências de leitura, não representam a quantidade de níveis. Escadas usam 64, 128 e 256 níveis reais.',
    }
