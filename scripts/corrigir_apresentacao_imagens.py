#!/usr/bin/env python3
"""Aplica correcoes pontuais nas imagens do deck SiDi, sem redesenhar os slides.

O arquivo atual usa uma unica imagem PNG ocupando cada slide. Por isso, este
script localiza a imagem associada a cada slide dentro do pacote PPTX, cobre
somente as regioes que precisam de ajuste e redesenha o conteudo corrigido com
Pillow. Todo o restante da imagem original e preservado pixel a pixel.

Por padrao, a apresentacao original nao e sobrescrita. A saida e criada em:

    powerpoint/apresentacao_sidi_automation_modelos_resultados_corrigida.pptx

Uso:

    python scripts/corrigir_apresentacao_imagens.py

Opcionalmente:

    python scripts/corrigir_apresentacao_imagens.py \
      --source powerpoint/apresentacao_sidi_automation_modelos_resultados.pptx \
      --output powerpoint/minha_apresentacao_corrigida.pptx \
      --export-images /tmp/slides_corrigidos

Use ``--overwrite`` somente quando quiser substituir uma saida ja existente.
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "powerpoint" / "apresentacao_sidi_automation_modelos_resultados.pptx"
DEFAULT_OUTPUT = ROOT / "powerpoint" / "apresentacao_sidi_automation_modelos_resultados_corrigida.pptx"

# As coordenadas abaixo foram medidas nas imagens originais, que possuem
# 1672 x 941 px. A classe SlideCanvas escala tudo proporcionalmente caso uma
# nova exportacao use outra resolucao com a mesma proporcao 16:9.
REF_W = 1672
REF_H = 941

WHITE = (255, 255, 255, 255)
BLACK = (20, 20, 20, 255)
DARK = (39, 45, 42, 255)
GRAY = (98, 108, 103, 255)
MID_GRAY = (205, 216, 209, 255)
GREEN = (0, 128, 55, 255)
DARK_GREEN = (0, 111, 47, 255)
LIGHT_GREEN = (239, 248, 241, 255)
LIGHTER_GREEN = (247, 252, 248, 255)

FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


class SlideCanvas:
    """Desenha usando coordenadas da imagem de referencia 1672 x 941."""

    def __init__(self, image: Image.Image) -> None:
        self.image = image.convert("RGBA")
        self.draw = ImageDraw.Draw(self.image)
        self.sx = self.image.width / REF_W
        self.sy = self.image.height / REF_H

    def x(self, value: float) -> int:
        return round(value * self.sx)

    def y(self, value: float) -> int:
        return round(value * self.sy)

    def box(self, coords: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = coords
        return self.x(x1), self.y(y1), self.x(x2), self.y(y2)

    def font(self, size: float, *, bold: bool = False) -> ImageFont.FreeTypeFont:
        path = FONT_BOLD if bold else FONT_REGULAR
        if not path.exists():
            raise FileNotFoundError(f"Fonte necessaria nao encontrada: {path}")
        return ImageFont.truetype(str(path), max(8, self.y(size)))

    def cover(
        self,
        coords: tuple[float, float, float, float],
        *,
        fill=WHITE,
        outline=None,
        width: float = 1.0,
        radius: float = 0,
    ) -> None:
        box = self.box(coords)
        if radius:
            self.draw.rounded_rectangle(
                box,
                radius=self.y(radius),
                fill=fill,
                outline=outline,
                width=max(1, self.x(width)),
            )
        else:
            self.draw.rectangle(
                box,
                fill=fill,
                outline=outline,
                width=max(1, self.x(width)),
            )

    def line(
        self,
        points: list[tuple[float, float]],
        *,
        fill=GREEN,
        width: float = 2,
    ) -> None:
        self.draw.line(
            [(self.x(x), self.y(y)) for x, y in points],
            fill=fill,
            width=max(1, self.x(width)),
            joint="curve",
        )

    def arrow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        fill=GREEN,
        width: float = 2,
    ) -> None:
        x1, y1 = start
        x2, y2 = end
        self.line([start, end], fill=fill, width=width)
        head = 7
        self.line([(x2 - head, y2 - 5), (x2, y2), (x2 - head, y2 + 5)], fill=fill, width=width)

    def dashed_vertical(
        self,
        x: float,
        y1: float,
        y2: float,
        *,
        fill=GRAY,
        width: float = 1.5,
        dash: float = 7,
        gap: float = 6,
    ) -> None:
        y = y1
        while y < y2:
            self.line([(x, y), (x, min(y + dash, y2))], fill=fill, width=width)
            y += dash + gap

    def circle(
        self,
        center: tuple[float, float],
        radius: float,
        *,
        fill=WHITE,
        outline=GREEN,
        width: float = 2,
    ) -> None:
        x, y = center
        self.draw.ellipse(
            self.box((x - radius, y - radius, x + radius, y + radius)),
            fill=fill,
            outline=outline,
            width=max(1, self.x(width)),
        )

    def text(
        self,
        value: str,
        coords: tuple[float, float, float, float],
        *,
        size: float,
        color=BLACK,
        bold: bool = False,
        align: str = "left",
        valign: str = "middle",
        spacing: float = 4,
    ) -> None:
        x1, y1, x2, y2 = self.box(coords)
        font = self.font(size, bold=bold)
        lines = value.splitlines() or [""]
        widths = [self.draw.textlength(line, font=font) for line in lines]
        line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
        spacing_px = self.y(spacing)
        total_height = len(lines) * line_height + max(0, len(lines) - 1) * spacing_px
        if valign == "top":
            cursor_y = y1
        elif valign == "bottom":
            cursor_y = y2 - total_height
        else:
            cursor_y = y1 + (y2 - y1 - total_height) / 2
        for line, line_width in zip(lines, widths):
            if align == "center":
                cursor_x = x1 + (x2 - x1 - line_width) / 2
            elif align == "right":
                cursor_x = x2 - line_width
            else:
                cursor_x = x1
            self.draw.text((round(cursor_x), round(cursor_y)), line, font=font, fill=color)
            cursor_y += line_height + spacing_px

    def small_card(
        self,
        coords: tuple[float, float, float, float],
        title: str,
        subtitle: str | None = None,
    ) -> None:
        self.cover(coords, fill=WHITE, outline=MID_GRAY, width=1, radius=10)
        x1, y1, x2, y2 = coords
        if subtitle:
            self.text(title, (x1 + 8, y1 + 7, x2 - 8, y1 + 30), size=15, color=DARK_GREEN, bold=True, align="center")
            self.text(subtitle, (x1 + 8, y1 + 31, x2 - 8, y2 - 6), size=11, color=DARK, align="center")
        else:
            self.text(title, (x1 + 8, y1 + 6, x2 - 8, y2 - 6), size=14, color=DARK, bold=True, align="center")


def _patch_output_index(canvas: SlideCanvas, formula_box, label_box) -> None:
    canvas.cover(formula_box, fill=WHITE)
    canvas.text("ŷₜ₊₁", formula_box, size=28, color=BLACK, align="center")
    canvas.cover(label_box, fill=WHITE)
    canvas.text("próximo mês (t+1)", label_box, size=14, color=DARK_GREEN, bold=True, align="center")


def patch_slide_4(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)

    # Terminologia da fonte de dados.
    c.cover((140, 314, 520, 350), fill=WHITE)
    c.text(
        "NLR/NSRDB — GOES Aggregated PSM v4",
        (144, 314, 520, 349),
        size=16,
        color=DARK,
    )

    # Substitui somente o cartao geografico incorreto por uma distribuicao
    # textual fiel: 8 EUA, 1 Mexico e 1 Brasil.
    c.cover((64, 365, 480, 681), fill=WHITE, outline=MID_GRAY, width=1, radius=14)
    c.text("10 localidades associadas a fábricas de VE", (82, 383, 462, 426), size=20, color=DARK_GREEN, bold=True, align="center")
    c.small_card((84, 446, 196, 535), "8", "EUA")
    c.small_card((216, 446, 328, 535), "1", "México")
    c.small_card((348, 446, 460, 535), "1", "Brasil")
    c.text(
        "Fábricas reais usadas apenas como referências geográficas.",
        (88, 558, 456, 608),
        size=14,
        color=DARK,
        align="center",
    )
    c.text(
        "Não são utilizados dados industriais das empresas.",
        (88, 612, 456, 660),
        size=13,
        color=GRAY,
        align="center",
    )

    # Explicita selecao, refit e teste no protocolo horario.
    rows = [
        ((1183, 579, 1597, 643), "seleção — treino: 2019–2022"),
        ((1183, 652, 1597, 715), "seleção — validação: 2023"),
        ((1183, 724, 1597, 786), "refit: 2019–2023  →  teste: 2024"),
    ]
    for box, label in rows:
        c.cover(box, fill=WHITE, outline=MID_GRAY, width=1, radius=9)
        c.text(label, (box[0] + 16, box[1] + 6, box[2] - 12, box[3] - 6), size=15, color=DARK, bold=True)
    return c.image


def patch_slide_5(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    _patch_output_index(c, (1514, 399, 1591, 461), (1424, 552, 1591, 584))
    return c.image


def patch_slide_6(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    _patch_output_index(c, (1513, 391, 1591, 451), (1420, 561, 1590, 592))
    return c.image


def patch_slide_7(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    _patch_output_index(c, (1504, 345, 1588, 409), (1438, 541, 1594, 570))
    c.cover((69, 549, 486, 596), fill=WHITE)
    c.text(
        "Ramo auxiliar: médias móveis • calendário • localidade",
        (76, 552, 480, 591),
        size=11,
        color=GRAY,
        align="center",
    )
    return c.image


def patch_slide_8(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    _patch_output_index(c, (1501, 372, 1586, 435), (1417, 557, 1592, 589))
    c.cover((84, 574, 449, 620), fill=WHITE)
    c.text(
        "Ramo auxiliar: médias móveis • calendário • localidade",
        (88, 578, 445, 615),
        size=10,
        color=GRAY,
        align="center",
    )
    return c.image


def patch_slide_9(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    _patch_output_index(c, (1500, 346, 1587, 410), (1417, 547, 1590, 579))

    # A implementacao possui tres camadas empilhadas, nao tres ramos paralelos.
    c.cover((504, 290, 1096, 596), fill=WHITE)
    c.text(
        "Implementação do projeto: camadas recorrentes empilhadas",
        (520, 302, 1080, 337),
        size=16,
        color=DARK_GREEN,
        bold=True,
        align="center",
    )
    cards = [
        ((520, 372, 650, 450), "Sequência", "12 meses"),
        ((680, 372, 810, 450), "Camada 1", "dilatação s=1"),
        ((840, 372, 970, 450), "Camada 2", "dilatação s=2"),
        ((1000, 372, 1090, 450), "Camada 3", "s=4"),
    ]
    for box, title, subtitle in cards:
        c.small_card(box, title, subtitle)
    for start, end in [((650, 411), (678, 411)), ((810, 411), (838, 411)), ((970, 411), (998, 411))]:
        c.arrow(start, end, width=2)
    c.cover((650, 497, 1030, 555), fill=LIGHTER_GREEN, outline=MID_GRAY, radius=8)
    c.text(
        "Ramo auxiliar: médias móveis • calendário • localidade",
        (664, 503, 1016, 548),
        size=12,
        color=DARK,
        align="center",
    )
    c.arrow((840, 556), (840, 580), width=2)
    c.text("fusão → previsão pontual", (720, 566, 960, 593), size=11, color=DARK_GREEN, bold=True, align="center")
    return c.image


def patch_slide_10(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)

    # Substitui o leque multi-mes por uma distribuicao de um unico proximo mes.
    c.cover((1125, 261, 1576, 598), fill=WHITE)
    c.text(
        "No experimento: distribuição para o próximo mês (t+1)",
        (1138, 275, 1562, 314),
        size=15,
        color=DARK_GREEN,
        bold=True,
        align="center",
    )
    c.line([(1160, 512), (1546, 512)], fill=GRAY, width=1.5)
    history = [(1170, 474), (1205, 447), (1240, 463), (1275, 427), (1310, 441), (1345, 402)]
    c.line(history, fill=DARK_GREEN, width=3)
    for point in history:
        c.circle(point, 4, fill=GREEN, outline=DARK_GREEN, width=1)
    c.dashed_vertical(1384, 334, 526, fill=GRAY)
    c.text("origem t", (1354, 526, 1414, 552), size=11, color=GRAY, align="center")
    # Distribuicao vertical no unico instante futuro.
    c.line([(1482, 364), (1482, 474)], fill=MID_GRAY, width=5)
    for y, label, radius in [(380, "P90", 5), (420, "P50", 7), (462, "P10", 5)]:
        c.circle((1482, y), radius, fill=GREEN if label == "P50" else LIGHT_GREEN, outline=DARK_GREEN, width=2)
        c.text(label, (1500, y - 14, 1555, y + 14), size=12, color=DARK_GREEN, bold=label == "P50")
    c.text("histórico observado", (1160, 540, 1348, 568), size=11, color=GRAY, align="center")
    c.text("t+1", (1450, 494, 1515, 520), size=13, color=DARK_GREEN, bold=True, align="center")
    return c.image


def patch_slide_11(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)

    # Para horizonte de um passo, cada amostra e um valor, nao uma trajetoria.
    c.cover((963, 285, 1128, 586), fill=WHITE)
    c.text("4. Valores futuros\namostrados", (970, 296, 1120, 350), size=14, color=DARK, bold=True, align="center")
    c.line([(1043, 380), (1043, 524)], fill=MID_GRAY, width=3)
    sample_points = [(1043, 392), (1043, 416), (1043, 447), (1043, 482), (1043, 515)]
    for index, point in enumerate(sample_points):
        c.circle(point, 5 if index != 2 else 7, fill=LIGHT_GREEN if index != 2 else GREEN, outline=DARK_GREEN, width=2)
    c.text("uma amostra = um valor em t+1", (972, 537, 1117, 572), size=10, color=GRAY, align="center")
    return c.image


def patch_slide_12(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)

    # TimesNet e pontual; remove a faixa visual que parecia intervalo preditivo.
    c.cover((1287, 275, 1590, 586), fill=WHITE)
    c.text("previsão pontual direta de 72 horas", (1296, 280, 1580, 315), size=14, color=DARK_GREEN, bold=True, align="center")
    c.line([(1310, 510), (1572, 510)], fill=GRAY, width=1.4)
    c.line([(1320, 330), (1320, 510)], fill=GRAY, width=1.4)
    history = [
        (1320, 450), (1340, 420), (1360, 464), (1380, 388), (1400, 430),
        (1420, 405), (1440, 462), (1460, 421),
    ]
    forecast = [
        (1460, 421), (1480, 378), (1500, 402), (1520, 370), (1540, 415),
        (1560, 389),
    ]
    c.line(history, fill=GRAY, width=2.5)
    c.line(forecast, fill=GREEN, width=3.5)
    c.dashed_vertical(1460, 326, 520, fill=GRAY)
    c.text("contexto (336 h)", (1305, 526, 1456, 554), size=11, color=GRAY, align="center")
    c.text("previsão (72 h)", (1464, 526, 1585, 554), size=11, color=DARK_GREEN, bold=True, align="center")
    c.text("saída determinística — sem intervalo probabilístico", (1300, 558, 1580, 582), size=10, color=GRAY, align="center")
    return c.image


def patch_slide_14(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    c.cover((45, 144, 1455, 211), fill=WHITE)
    c.text(
        "Resultado mensal: uma referência simples liderou o ranking",
        (47, 146, 1450, 207),
        size=37,
        color=BLACK,
        bold=True,
    )
    c.cover((49, 780, 1417, 838), fill=LIGHT_GREEN, outline=MID_GRAY, width=1, radius=9)
    c.text(
        "No experimento mensal, a climatologia foi o melhor método.",
        (90, 790, 1390, 830),
        size=18,
        color=DARK_GREEN,
        bold=True,
        align="center",
    )
    return c.image


def patch_slide_16(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    c.cover((70, 368, 318, 468), fill=WHITE)
    c.text("Uma referência\nsimples liderou", (77, 375, 312, 458), size=21, color=BLACK, bold=True, align="center")
    c.cover((72, 475, 318, 559), fill=WHITE)
    c.text(
        "A climatologia obteve o menor\nmacro-MAE mensal.",
        (78, 484, 312, 552),
        size=14,
        color=DARK,
        align="center",
    )
    return c.image


def patch_slide_17(image: Image.Image) -> Image.Image:
    c = SlideCanvas(image)
    c.cover((48, 807, 1508, 849), fill=WHITE)
    c.text(
        "Exemplos potenciais de machine learning em automação — não avaliados neste projeto.",
        (92, 808, 1500, 845),
        size=15,
        color=DARK,
    )
    return c.image


PATCHERS = {
    4: patch_slide_4,
    5: patch_slide_5,
    6: patch_slide_6,
    7: patch_slide_7,
    8: patch_slide_8,
    9: patch_slide_9,
    10: patch_slide_10,
    11: patch_slide_11,
    12: patch_slide_12,
    14: patch_slide_14,
    16: patch_slide_16,
    17: patch_slide_17,
}


def _normalizar_target_relacionamento(rel_path: str, target: str) -> str:
    """Resolve ``../media/imageX.png`` a partir de ``ppt/slides/slideX.xml``."""
    slide_name = PurePosixPath(rel_path).name.removesuffix(".rels")
    base = PurePosixPath("ppt/slides") / slide_name
    parts: list[str] = []
    for part in (base.parent / target).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part not in {".", ""}:
            parts.append(part)
    return "/".join(parts)


def mapear_imagens_por_slide(archive: zipfile.ZipFile) -> dict[int, str]:
    mapping: dict[int, str] = {}
    names = set(archive.namelist())
    slide = 1
    while True:
        rel_path = f"ppt/slides/_rels/slide{slide}.xml.rels"
        if rel_path not in names:
            break
        root = ET.fromstring(archive.read(rel_path))
        targets = [
            node.attrib.get("Target", "")
            for node in root.findall("r:Relationship", REL_NS)
            if node.attrib.get("Type") == REL_IMAGE
        ]
        if len(targets) != 1:
            raise ValueError(
                f"Slide {slide}: esperado exatamente um relacionamento de imagem; "
                f"encontrados {len(targets)}."
            )
        image_path = _normalizar_target_relacionamento(rel_path, targets[0])
        if image_path not in names:
            raise ValueError(f"Slide {slide}: imagem nao encontrada no PPTX: {image_path}")
        mapping[slide] = image_path
        slide += 1
    return mapping


def corrigir_pptx(
    source: Path,
    output: Path,
    *,
    overwrite: bool,
    export_images: Path | None,
) -> tuple[int, list[int]]:
    if not source.is_file():
        raise FileNotFoundError(f"Apresentacao de origem nao encontrada: {source}")
    if source.resolve() == output.resolve():
        raise ValueError("A saida deve ser diferente da origem; o original e preservado por seguranca.")
    if output.exists() and not overwrite:
        raise FileExistsError(
            f"A saida ja existe: {output}. Use --overwrite para substitui-la."
        )

    replacements: dict[str, bytes] = {}
    modified_slides: list[int] = []
    with zipfile.ZipFile(source, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise zipfile.BadZipFile(f"Entrada corrompida; primeiro membro invalido: {bad}")
        mapping = mapear_imagens_por_slide(archive)
        missing = sorted(set(PATCHERS) - set(mapping))
        if missing:
            raise ValueError(f"A apresentacao nao possui os slides esperados: {missing}")

        if export_images:
            export_images.mkdir(parents=True, exist_ok=True)

        for slide_number, patcher in PATCHERS.items():
            image_path = mapping[slide_number]
            original = Image.open(BytesIO(archive.read(image_path))).convert("RGBA")
            corrected = patcher(original)
            buffer = BytesIO()
            corrected.save(buffer, format="PNG", optimize=False)
            replacements[image_path] = buffer.getvalue()
            modified_slides.append(slide_number)
            if export_images:
                corrected.save(export_images / f"slide_{slide_number:02d}_corrigido.png")

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}-",
            suffix=output.suffix,
            dir=output.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)

        try:
            with zipfile.ZipFile(temporary, "w") as destination:
                for info in archive.infolist():
                    data = replacements.get(info.filename, archive.read(info.filename))
                    destination.writestr(info, data)
            with zipfile.ZipFile(temporary, "r") as validation:
                bad = validation.testzip()
                if bad:
                    raise zipfile.BadZipFile(
                        f"Saida invalida; primeiro membro com erro: {bad}"
                    )
                if len(mapear_imagens_por_slide(validation)) != len(mapping):
                    raise ValueError("A quantidade de slides mudou durante a regravacao.")
            if output.exists():
                output.unlink()
            temporary.replace(output)
            # Mantem as permissoes praticas do arquivo de origem. O arquivo
            # temporario nasce restrito por seguranca, mas a copia final deve
            # se comportar como os demais artefatos do projeto.
            output.chmod(source.stat().st_mode & 0o777)
        finally:
            temporary.unlink(missing_ok=True)

    return len(mapping), modified_slides


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aplica correcoes pontuais nas imagens internas do deck SiDi."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--export-images",
        type=Path,
        help="Opcional: pasta para exportar somente as imagens que foram alteradas.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite substituir um arquivo de saida que ja exista.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    slide_count, modified = corrigir_pptx(
        args.source.resolve(),
        args.output.resolve(),
        overwrite=args.overwrite,
        export_images=args.export_images.resolve() if args.export_images else None,
    )
    print(f"Apresentacao corrigida: {args.output.resolve()}")
    print(f"Slides no arquivo: {slide_count}")
    print("Slides alterados pontualmente: " + ", ".join(map(str, modified)))
    if args.export_images:
        print(f"Imagens de verificacao: {args.export_images.resolve()}")


if __name__ == "__main__":
    main()
