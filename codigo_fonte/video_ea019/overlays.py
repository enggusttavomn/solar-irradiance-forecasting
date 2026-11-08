"""Deterministic Portuguese text overlays for the EA019 scientific video.

Only the Python standard library is required.  The generated ASS file is burned
over the 3D render with FFmpeg/libass; it never invents numerical result curves.
Coordinates are expressed on the final 1920 x 1080 canvas.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / "documentacao/relatorio_final_ea019/video/trecho_animado_v2/plano_trecho_animado_v2.json"
DEFAULT_SRT = DEFAULT_PLAN.with_name("legendas_trecho_animado_v2.srt")
DEFAULT_RESULTS = ROOT / "resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina/classificacoes_modelos_disciplina.csv"

WHITE = "F3F6FB"
MUTED = "AAB9C9"
CYAN = "67DDED"
GOLD = "FFD38A"
CORAL = "FFA197"
VIOLET = "C39AF3"
MODEL_COLORS = {"Transformer": CYAN, "Informer": VIOLET, "LSTM": CORAL}


def ass_color(rgb: str, alpha: str = "00") -> str:
    """Return ASS AABBGGRR notation from an RGB hex string."""
    rgb = rgb.lstrip("#")
    if len(rgb) != 6 or len(alpha) != 2:
        raise ValueError("Expected six RGB hex digits and two alpha hex digits")
    int(rgb + alpha, 16)
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def timestamp(seconds: float | Decimal) -> str:
    cs = round(Decimal(str(seconds)) * 100)
    if cs < 0:
        raise ValueError("Negative time")
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def literal(text: str) -> str:
    """Keep source text from introducing ASS override blocks."""
    text = text.replace("\\N", "\n").replace("\r\n", "\n")
    if "{" in text or "}" in text:
        raise ValueError("Overlay source must not contain ASS override braces")
    if "\\" in text:
        raise ValueError("Use actual newlines, not ASS escape sequences")
    return text.replace("\n", r"\N")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def read_srt(path: str | Path) -> list[Cue]:
    content = Path(path).read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\r?\n\s*\r?\n", content)
    cues: list[Cue] = []
    for index, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3 or int(lines[0]) != index:
            raise ValueError(f"Invalid SRT cue {index}")
        times = re.fullmatch(r"(\d+):(\d{2}):(\d{2}),(\d{3}) --> (\d+):(\d{2}):(\d{2}),(\d{3})", lines[1])
        if not times:
            raise ValueError(f"Invalid SRT timing {index}")
        v = list(map(int, times.groups()))
        start = v[0] * 3600 + v[1] * 60 + v[2] + v[3] / 1000
        end = v[4] * 3600 + v[5] * 60 + v[6] + v[7] / 1000
        if end <= start or (cues and start < cues[-1].end):
            raise ValueError(f"Overlapping or empty SRT cue {index}")
        caption_lines = lines[2:]
        if len(caption_lines) > 2 or max(map(len, caption_lines)) > 42:
            raise ValueError(f"Caption {index} exceeds two lines / 42 columns")
        cues.append(Cue(start, end, "\n".join(caption_lines)))
    return cues


STYLES = f"""[Script Info]
Title: EA019 scientific animation - deterministic text overlay
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Segoe UI,44,{ass_color(WHITE)},&H00FFFFFF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,3,12,0,2,110,110,80,1
Style: Header,Segoe UI,58,{ass_color(WHITE)},&H00FFFFFF,&HCC000000,&H00000000,-1,0,0,0,100,100,0,0,1,0.7,0,7,0,0,0,1
Style: Eyebrow,Segoe UI,24,{ass_color(CYAN)},&H00FFFFFF,&HCC000000,&H00000000,0,0,0,0,100,100,1.4,0,1,0.5,0,7,0,0,0,1
Style: Text,Segoe UI,40,{ass_color(WHITE)},&H00FFFFFF,&HCC000000,&H00000000,0,0,0,0,100,100,0,0,1,0.7,0,7,0,0,0,1
Style: Small,Segoe UI,26,{ass_color(MUTED)},&H00FFFFFF,&HCC000000,&H00000000,0,0,0,0,100,100,0,0,1,0.5,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


class Overlay:
    def __init__(self, duration: float):
        self.duration = duration
        self.events: list[str] = []
        self.checks: list[dict] = []

    def text(self, start: float, end: float, text: str, *, x: int, y: int,
             size: int = 40, color: str = WHITE, style: str = "Text",
             align: int = 7, layer: int = 4, bold: bool = False,
             fade_ms: int = 220) -> None:
        if not (0 <= start < end <= self.duration):
            raise ValueError(f"Out-of-range event {start}-{end}: {text}")
        if not (0 <= x <= 1920 and 0 <= y <= 1080):
            raise ValueError("Overlay anchor outside canvas")
        tags = f"\\an{align}\\pos({x},{y})\\fs{size}\\c{ass_color(color)}&\\b{1 if bold else 0}\\fad({fade_ms},{fade_ms})"
        self.events.append(f"Dialogue: {layer},{timestamp(start)},{timestamp(end)},{style},,0,0,0,,{{{tags}}}{literal(text)}")
        self.checks.append({"start": start, "end": end, "text": text,
                            "anchor": [x, y], "font_size": size,
                            "layer": layer, "style": style})

    def caption(self, cue: Cue) -> None:
        lines = cue.text.splitlines()
        if len(lines) > 2 or max(map(len, lines)) > 42:
            raise ValueError("Caption too long")
        self.text(cue.start, cue.end, cue.text, x=960, y=985, size=44,
                  style="Caption", align=2, layer=10, fade_ms=100)

    def header(self, start: float, end: float, title: str, index: str) -> None:
        self.text(start, end, index, x=110, y=46, size=23, color=CYAN,
                  style="Eyebrow", layer=3)
        self.text(start, end, title, x=110, y=95, size=58,
                  style="Header", layer=3, bold=True)

    def source(self, start: float, end: float, text: str) -> None:
        self.text(start, end, text, x=110, y=810, size=24, color=MUTED,
                  style="Small", layer=4)

    def write(self, path: str | Path) -> dict:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STYLES + "\n".join(self.events) + "\n", encoding="utf-8-sig")
        return {"path": str(path.resolve()), "duration_seconds": self.duration,
                "event_count": len(self.events),
                "caption_count": sum(c["style"] == "Caption" for c in self.checks),
                "canvas": [1920, 1080], "font": "Segoe UI",
                "regions": {"header": [110, 46, 1810, 180],
                            "main_content": [110, 220, 1810, 790],
                            "source_line": [110, 810],
                            "caption_anchor": [960, 985],
                            "caption_reserved_band": [100, 850, 1820, 1020]},
                "events": self.checks}


PILOT_CUES = [
    Cue(0, 5, "A irradiância global horizontal, ou GHI,"),
    Cue(5, 10, "é a potência solar recebida por área\nem uma superfície horizontal."),
    Cue(10, 14, "Sua unidade é watt por metro quadrado."),
    Cue(14, 20, "Parte chega diretamente do Sol;\nparte é espalhada pela atmosfera."),
    Cue(20, 25, "Essa variação pode ser representada\npor uma série temporal."),
    Cue(25, 30, "Usamos o histórico para tentar prever\nos valores futuros de GHI."),
]


def write_pilot_ass(path: str | Path, *, include_captions: bool = True) -> dict:
    overlay = Overlay(30)
    overlay.header(0, 20, "Irradiância global horizontal", "RECURSO SOLAR · GHI")
    overlay.header(20, 30, "Do passado à previsão", "SÉRIES TEMPORAIS")
    overlay.text(0, 30, "PILOTO VISUAL · 30 s", x=1810, y=48, size=22,
                 color=MUTED, style="Small", align=9, layer=3)
    overlay.text(3, 20, "GHI", x=1300, y=350, size=50, color=GOLD, bold=True)
    overlay.text(5, 20, "Superfície horizontal", x=1370, y=675, size=30, color=WHITE)
    overlay.text(9.5, 20, "W/m²", x=1380, y=740, size=47, color=GOLD)
    overlay.text(14, 20, "Direta", x=1210, y=405, size=29, color=GOLD)
    overlay.text(14, 20, "Difusa", x=1440, y=485, size=29, color=GOLD)
    overlay.text(22, 30, "Histórico de GHI", x=400, y=300, size=34, color=WHITE, align=8)
    overlay.text(25, 30, "Presente", x=1160, y=300, size=32, color=MUTED, align=8)
    overlay.text(25, 30, "Futuro", x=1500, y=300, size=34, color=CYAN, align=8)
    overlay.source(0, 30, "Ilustração conceitual")
    if include_captions:
        for cue in PILOT_CUES:
            overlay.caption(cue)
    return overlay.write(path)


def load_results(path: str | Path = DEFAULT_RESULTS) -> dict[str, dict[str, dict]]:
    expected = {"hourly_72_extension": 72, "daily_30": 30,
                "monthly_1": 1, "monthly_6": 6}
    result = {task: {} for task in expected}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row["regime"] == "atual" and row["particao"] == "teste"
                    and row["selecionado"] == "True" and row["tarefa"] in expected
                    and int(row["horizonte"]) == expected[row["tarefa"]]):
                task, model = row["tarefa"], row["modelo"]
                if model in result[task]:
                    raise ValueError(f"Duplicate selected result: {task}/{model}")
                result[task][model] = {"mae": Decimal(row["MAE_wm2"]),
                                       "variant": "Controle" if row["variante"] == "sem_quantizacao" else row["variante"].upper(),
                                       "position": int(row["posicao"])}
    if any(set(rows) != set(MODEL_COLORS) for rows in result.values()):
        raise ValueError("Missing models or selected result rows")
    return result


def pretty(value: Decimal, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def opening(overlay: Overlay) -> None:
    overlay.text(0, 6, "UNIVERSIDADE ESTADUAL DE CAMPINAS", x=120, y=185, size=35, color=MUTED)
    overlay.text(0, 6, "Faculdade de Engenharia Elétrica e de Computação", x=120, y=245, size=30, color=MUTED)
    overlay.text(0, 6, "Gustavo de Melo Nascimento", x=120, y=375, size=58, bold=True)
    overlay.text(0, 6, "RA 239679 · Engenharia Elétrica (41)", x=120, y=465, size=35)
    overlay.text(6, 14, "Previsão multirresolução de\nirradiância global horizontal\nem localidades associadas à\nfabricação de veículos elétricos", x=120, y=215, size=50, bold=True)
    overlay.text(6, 14, "Avaliação comparativa de Transformer, Informer e LSTM", x=120, y=525, size=34, color=GOLD)
    overlay.text(14, 20, "Orientador: Prof. Dr. Gustavo Fraidenraich", x=120, y=275, size=43)
    overlay.text(14, 20, "Coorientador: Thales Wulfert Cabral", x=120, y=365, size=43)
    overlay.text(14, 20, "EA019 · 2º semestre de 2026", x=120, y=505, size=35, color=GOLD)
    overlay.text(14, 20, "Campinas, 2026", x=120, y=565, size=32, color=MUTED)


def result_panel(overlay: Overlay, start: float, end: float, title: str,
                 rows: dict[str, dict], *, exploratory: bool = False) -> None:
    overlay.text(start, end, title, x=180, y=245, size=45, bold=True)
    overlay.text(start, end, "Macro-MAE (W/m²)", x=1335, y=285, size=27, color=MUTED, align=8)
    for i, model in enumerate(("Transformer", "Informer", "LSTM")):
        y = 365 + i * 128
        row = rows[model]
        row_start = start + .5 + i * .8
        overlay.text(row_start, end, model, x=210, y=y, size=44,
                     color=MODEL_COLORS[model], bold=True)
        overlay.text(row_start, end, row["variant"], x=730, y=y + 12, size=31, color=MUTED)
        overlay.text(row_start, end, pretty(row["mae"]), x=1445, y=y - 9,
                     size=63, color=MODEL_COLORS[model] if row["position"] == 1 else WHITE,
                     align=9, bold=row["position"] == 1)
    if exploratory:
        overlay.text(start, end, "Avaliação exploratória", x=180, y=745, size=28, color=VIOLET)
    overlay.source(start, end, "Fonte: relatório, Tabela 6 · Configurações selecionadas na validação")


def full_content(overlay: Overlay, results: dict[str, dict[str, dict]]) -> None:
    opening(overlay)
    # Physical concept and illustrative time series.
    overlay.text(24, 44, "GHI", x=1300, y=350, size=50, color=GOLD, bold=True)
    overlay.text(25, 44, "Superfície horizontal", x=1370, y=675, size=30)
    overlay.text(29, 44, "W/m²", x=1380, y=740, size=47, color=GOLD)
    overlay.text(32, 43, "Radiação direta + difusa", x=1200, y=480, size=30, color=GOLD)
    overlay.text(45, 55, "Histórico de GHI", x=400, y=300, size=34, align=8)
    overlay.text(48, 55, "Presente", x=1160, y=300, size=32, color=MUTED, align=8)
    overlay.text(48, 55, "Futuro", x=1500, y=300, size=34, color=CYAN, align=8)
    overlay.source(20, 55, "Ilustração conceitual · Fonte: relatório, seção 4.1")
    overlay.text(55, 62, "Prever o recurso solar\napoia o planejamento", x=160, y=300, size=52, bold=True)
    for model, x in (("LSTM", 340), ("Transformer", 960), ("Informer", 1580)):
        overlay.text(62, 75, model, x=x, y=625, size=40, color=MODEL_COLORS[model], align=8)
    overlay.source(55, 75, "Escalas temporais · representação da entrada · histórico de treinamento")
    # Geographic plot is created in 3D; counts and acquisition scope remain frontal.
    overlay.text(77, 93, "10 localidades", x=1260, y=300, size=53, color=GOLD, bold=True)
    overlay.text(79, 93, "1 Brasil\n8 Estados Unidos\n1 México", x=1260, y=405, size=37)
    overlay.text(87, 93, "Detroit · ampliação", x=265, y=515, size=24, color=MUTED)
    overlay.text(87.5, 93, "GM Factory Zero", x=500, y=595, size=24)
    overlay.text(87.5, 93, "Ford Rouge EV Center", x=500, y=680, size=24)
    overlay.text(93, 104, "Históricos de GHI", x=1260, y=300, size=38, color=GOLD)
    overlay.text(93, 104, "Ilustração conceitual", x=1260, y=375, size=30, color=MUTED)
    overlay.text(104, 115, "Histórico de GHI", x=280, y=285, size=28)
    overlay.text(104, 115, "Identificação aprendida", x=280, y=550, size=28, color=CYAN)
    overlay.text(104, 115, "Modelo compartilhado", x=795, y=325, size=26, color=CYAN)
    overlay.text(104, 115, "Histórico de GHI + identificação da localidade", x=960, y=730, size=38, align=8)
    overlay.source(75, 115, "Dados: NSRDB · Localidades e coordenadas: relatório, Tabela 1")
    # One prediction task at a time, leaving the central-lower area for the window.
    tasks = [(115, 123, "Horária", "336 h → 72 h"),
             (123, 131, "Diária", "365 d → 30 d"),
             (131, 139, "Mensal · um passo", "12 meses → 1 mês"),
             (139, 150, "Mensal · seis passos", "12 meses → 6 meses")]
    for start, end, name, values in tasks:
        overlay.text(start, end, name, x=960, y=240, size=39, color=MUTED, align=8)
        overlay.text(start, end, values, x=960, y=310, size=73, color=CYAN, align=8, bold=True)
    overlay.source(139, 150, "Seis passos: tarefa exploratória · Redes treinadas separadamente")
    # Chronological stages; all text stays above the subtitle band.
    stages = [(150, 160, 315, "Treinamento inicial", "2019–2022"),
              (158, 169, 745, "Validação", "2023"),
              (166, 181, 1175, "Novo ajuste", "2019–2023"),
              (174, 190, 1605, "Teste retrospectivo", "2024")]
    for start, end, x, name, years in stages:
        overlay.text(start, end, name, x=x, y=355, size=31, color=MUTED, align=8)
        overlay.text(start, end, years, x=x, y=430, size=47, color=CYAN, align=8, bold=True)
    overlay.text(177, 190, "Houve exposição anterior ao período de teste", x=960, y=745, size=31, color=GOLD, align=8)
    overlay.source(150, 190, "Fonte: relatório, seções 3.4, 3.6 e 5.7 · Avaliação retrospectiva")
    # Architectural labels are intentionally concise; the diagrams carry the idea.
    for start, end, model, caption in (
        (190, 208, "LSTM", "Memória temporal"),
        (208, 226, "Transformer", "Atenção entre posições"),
        (226, 245, "Informer", "ProbSparse + redução temporal")):
        overlay.text(start, end, model, x=960, y=255, size=50, color=MODEL_COLORS[model], align=8, bold=True)
        overlay.text(start, end, caption, x=960, y=690, size=35, color=MODEL_COLORS[model], align=8)
    overlay.text(235, 245, "Na implementação: atenção cruzada completa", x=960, y=750, size=26, color=MUTED, align=8)
    overlay.source(190, 245, "Esquemas simplificados · Fonte: relatório, seções 4.2–4.4")
    for start, end, text in ((245, 250, "Contínuo"), (250, 260, "Q64"), (260, 270, "Q128"), (270, 280, "Q256")):
        overlay.text(start, end, text, x=1460, y=300, size=56, color=CYAN, align=8, bold=True)
    overlay.text(251, 280, "Somente a entrada de GHI", x=1460, y=600, size=32, align=8)
    overlay.text(258, 280, "Pesos e saída contínuos", x=1460, y=665, size=32, color=MUTED, align=8)
    overlay.source(245, 280, "Clipping + arredondamento · Reconstrução em float32 · Fonte: relatório, seção 3.5")
    overlay.text(281, 294, "MAE", x=1450, y=300, size=74, color=CYAN, bold=True, align=8)
    overlay.text(281, 294, "W/m²", x=1450, y=410, size=45, color=MUTED, align=8)
    overlay.text(294, 302, "Mesmo peso por localidade", x=960, y=260, size=45, align=8)
    overlay.text(302, 310, "Até 72 h = passos 1 a 72", x=960, y=260, size=45, color=CYAN, align=8)
    overlay.source(280, 310, "Exemplo didático da métrica · Fonte: relatório, seção 3.7")
    for start, end, title, task in (
        (310, 322, "Horária · até 72 horas", "hourly_72_extension"),
        (322, 334, "Diária · até 30 dias", "daily_30"),
        (334, 346, "Mensal · um passo", "monthly_1"),
        (346, 358, "Mensal · até seis passos", "monthly_6")):
        result_panel(overlay, start, end, title, results[task], exploratory=task == "monthly_6")
    overlay.text(358, 370, "Vantagens pequenas sobre a LSTM", x=960, y=255, size=48, align=8, bold=True)
    for task, x, title in (("hourly_72_extension", 550, "Horária · até 72 h"), ("daily_30", 1370, "Diária · até 30 d")):
        delta = results[task]["LSTM"]["mae"] - results[task]["Transformer"]["mae"]
        overlay.text(358, 370, pretty(delta) + " W/m²", x=x, y=410, size=65, color=CYAN, align=8, bold=True)
        overlay.text(358, 370, title, x=x, y=510, size=34, color=MUTED, align=8)
    overlay.text(363, 370, "Diária: LSTM lidera até 1, 3, 7 e 14 dias", x=960, y=700, size=34, color=CORAL, align=8)
    overlay.source(358, 370, "Diferenças descritivas · Fonte: relatório, seções 5.1–5.3")
    overlay.text(370, 378, "Quantização:\nsem benefício universal", x=960, y=315, size=54, align=8, bold=True)
    overlay.text(372, 378, "5 melhoram · 4 pioram · 3 mantêm o controle", x=960, y=540, size=33, color=MUTED, align=8)
    overlay.source(370, 378, "Condição selecionada na validação e observada no teste de 2024 · Relatório, Tabela 7")
    overlay.text(378, 390, "11 de 12", x=960, y=310, size=94, color=GOLD, align=8, bold=True)
    overlay.text(378, 390, "controles com menor MAE no histórico longo", x=960, y=470, size=41, align=8)
    overlay.text(378, 390, "Teste histórico pareado, separado de 2024", x=960, y=630, size=33, color=MUTED, align=8)
    overlay.source(378, 390, "Associação observada; efeito causal não isolado · Fonte: relatório, Tabela 8")
    for start, end, title, subtitle in (
        (390, 395, "Resultados descritivos", "Sem demonstração de significância estatística"),
        (395, 400, "Horário: uma semente", "Seis meses: avaliação exploratória"),
        (400, 405, "Alvos sobrepostos", "Localidades inéditas não foram avaliadas")):
        overlay.text(start, end, title, x=960, y=335, size=56, color=GOLD, align=8, bold=True)
        overlay.text(start, end, subtitle, x=960, y=505, size=38, align=8)
    overlay.source(390, 405, "Fonte: relatório, seção 5.7")
    overlay.text(405, 415, "Transformer", x=530, y=345, size=52, color=CYAN, align=8, bold=True)
    overlay.text(405, 415, "Horária e diária", x=530, y=445, size=39, align=8)
    overlay.text(405, 415, "Horizontes completos", x=530, y=510, size=30, color=MUTED, align=8)
    overlay.text(405, 415, "Informer", x=1390, y=345, size=52, color=VIOLET, align=8, bold=True)
    overlay.text(405, 415, "Tarefas mensais", x=1390, y=445, size=39, align=8)
    overlay.text(405, 415, "Nas configurações avaliadas", x=960, y=700, size=31, color=MUTED, align=8)
    overlay.source(405, 415, "Fonte: relatório, Tabela 6 e conclusão")


HEADERS = {
    2: ("Irradiância global horizontal", "RECURSO SOLAR · GHI"),
    3: ("Por que prever o recurso solar?", "OBJETIVO"),
    4: ("Dos dados às séries temporais", "DADOS · NSRDB"),
    5: ("Quatro tarefas de previsão", "PASSADO → FUTURO"),
    6: ("Uma comparação retrospectiva", "TREINAMENTO · VALIDAÇÃO · TESTE"),
    7: ("Três formas de aprender com o passado", "LSTM · TRANSFORMER · INFORMER"),
    8: ("A representação da entrada", "QUANTIZAÇÃO"),
    9: ("Como ler o erro de previsão", "AVALIAÇÃO · MACRO-MAE"),
    10: ("O desempenho nas quatro tarefas", "RESULTADOS · TESTE DE 2024"),
    11: ("O que muda com a entrada e o histórico", "ANÁLISES COMPLEMENTARES"),
    12: ("Limites da interpretação", "ESCOPO DAS CONCLUSÕES"),
    13: ("A escolha depende da tarefa", "SÍNTESE"),
}


def write_full_ass(plan_path: str | Path, srt_path: str | Path, path: str | Path,
                   *, results_path: str | Path = DEFAULT_RESULTS,
                   include_captions: bool = True,
                   include_content: bool = True) -> dict:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if plan["duration_seconds"] != 415 or len(plan["scenes"]) != 13:
        raise ValueError("This overlay layout targets the 415-second v2 animated cut")
    if any(s["format"] == "camera" for s in plan["scenes"]):
        raise ValueError("Camera scenes must not be present in the animated cut")
    overlay = Overlay(415)
    for scene in plan["scenes"]:
        if scene["id"] in HEADERS:
            title, eyebrow = HEADERS[scene["id"]]
            overlay.header(scene["start_seconds"], scene["end_seconds"], title, eyebrow)
    if include_content:
        full_content(overlay, load_results(results_path))
    if include_captions:
        for cue in read_srt(srt_path):
            overlay.caption(cue)
    report = overlay.write(path)
    report["results_source"] = str(Path(results_path).resolve())
    report["subtitle_source"] = str(Path(srt_path).resolve())
    report["timing_status"] = "provisional_script_timing_no_recorded_audio"
    return report


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--srt", type=Path, default=DEFAULT_SRT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--no-content", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = write_pilot_ass(args.output, include_captions=not args.no_captions) if args.pilot else write_full_ass(
        args.plan, args.srt, args.output, results_path=args.results,
        include_captions=not args.no_captions, include_content=not args.no_content)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "events"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
