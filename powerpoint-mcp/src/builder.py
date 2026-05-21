"""Aspose.Slides primitives used by the REST API.

Per-element shape construction against an in-memory `slides.Presentation`.
Coords arrive in CSS pixels relative to a virtual slide canvas
(usually 1920x1080) and are mapped to Aspose's EMU/point coordinate
system using the live presentation's `slide_size` so layout-probe output
lands at the right place on a 13.333"×7.5" slide.
"""

from __future__ import annotations

import base64
import io
from typing import Iterable

import aspose.slides as slides
from aspose.pydrawing import Color

from .models import (
    BBoxModel,
    ChartShapeRequest,
    GradientModel,
    ImageShapeRequest,
    ParagraphModel,
    SvgShapeRequest,
    TableShapeRequest,
    TextRunModel,
    TextShapeRequest,
)


# 1 inch = 72 points; default Aspose slide is 13.333"x7.5" = 960x540 pt for 16:9.
# We read the actual size from the presentation each call so a future
# resize keeps the math correct.


def _px_to_pt(value_px: float, canvas_px: float, slide_pt: float) -> float:
    return value_px * (slide_pt / canvas_px)


def _bbox_to_pt(bbox: BBoxModel, canvas_w: float, canvas_h: float,
                slide_w_pt: float, slide_h_pt: float) -> tuple[float, float, float, float]:
    return (
        _px_to_pt(bbox.x, canvas_w, slide_w_pt),
        _px_to_pt(bbox.y, canvas_h, slide_h_pt),
        _px_to_pt(bbox.w, canvas_w, slide_w_pt),
        _px_to_pt(bbox.h, canvas_h, slide_h_pt),
    )


def _hex_to_color(hex_str: str) -> Color:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return Color.from_argb(255, r, g, b)


def add_blank_slide(
    pres: slides.Presentation,
    bg_color: str | None,
    bg_gradient: GradientModel | None = None,
) -> int:
    """Append a blank slide; return its 0-based index. Gradient wins
    over solid color when both are provided."""
    blank_layout = None
    for layout in pres.layout_slides:
        if layout.layout_type == slides.SlideLayoutType.BLANK:
            blank_layout = layout
            break
    if blank_layout is None:
        blank_layout = pres.layout_slides[0]

    slide = pres.slides.add_empty_slide(blank_layout)

    if bg_gradient and bg_gradient.stops:
        _apply_gradient_fill(slide.background, bg_gradient)
    elif bg_color:
        slide.background.type = slides.BackgroundType.OWN_BACKGROUND
        slide.background.fill_format.fill_type = slides.FillType.SOLID
        slide.background.fill_format.solid_fill_color.color = _hex_to_color(bg_color)

    return pres.slides.index_of(slide)


def _apply_gradient_fill(background, gradient: GradientModel) -> None:
    background.type = slides.BackgroundType.OWN_BACKGROUND
    background.fill_format.fill_type = slides.FillType.GRADIENT
    gf = background.fill_format.gradient_format
    if gradient.type == "linear":
        gf.gradient_shape = slides.GradientShape.LINEAR
        # CSS angles: 0° = up, 90° = right. Aspose `gradient_direction`
        # only has 8 cardinal values; for arbitrary angles we set
        # linear_gradient_angle which is degrees clockwise from up.
        gf.linear_gradient_angle = float(gradient.angle) % 360
    else:  # radial
        gf.gradient_shape = slides.GradientShape.RECTANGLE
    # Replace default stops with ours.
    while gf.gradient_stops.count > 0:
        gf.gradient_stops.remove_at(0)
    for stop in gradient.stops:
        # Aspose's add() takes a position percent 0-100 and color.
        gf.gradient_stops.add(float(stop.offset) * 100.0, _hex_to_color(stop.color))


def _set_canvas_size(pres: slides.Presentation, width_px: float, height_px: float) -> None:
    """Set 16:9 slide size; the per-axis px→pt math uses the result."""
    aspect = width_px / height_px if height_px else (16 / 9)
    # Keep PowerPoint's standard widescreen: 13.333" wide @ 72pt = 960pt.
    width_pt = 960.0
    height_pt = width_pt / aspect
    pres.slide_size.set_size(width_pt, height_pt, slides.SlideSizeScaleType.DO_NOT_SCALE)


def create_empty_presentation(width_px: float, height_px: float) -> slides.Presentation:
    pres = slides.Presentation()
    _set_canvas_size(pres, width_px, height_px)
    # Default Aspose presentations include one blank slide — drop it.
    while pres.slides.length > 0:
        pres.slides.remove_at(0)
    return pres


def add_text_shape(
    pres: slides.Presentation,
    slide_index: int,
    req: TextShapeRequest,
    canvas_w_px: float,
    canvas_h_px: float,
) -> int:
    slide = pres.slides[slide_index]
    slide_w_pt = float(pres.slide_size.size.width)
    slide_h_pt = float(pres.slide_size.size.height)

    x, y, w, h = _bbox_to_pt(req.bbox, canvas_w_px, canvas_h_px, slide_w_pt, slide_h_pt)
    shape = slide.shapes.add_auto_shape(slides.ShapeType.RECTANGLE, x, y, w, h)
    shape.line_format.fill_format.fill_type = slides.FillType.NO_FILL

    if req.bg_color:
        shape.fill_format.fill_type = slides.FillType.SOLID
        shape.fill_format.solid_fill_color.color = _hex_to_color(req.bg_color)
    else:
        shape.fill_format.fill_type = slides.FillType.NO_FILL

    tf = shape.text_frame
    tf.text_frame_format.autofit_type = slides.TextAutofitType.NONE
    tf.text_frame_format.wrap_text = slides.NullableBool.TRUE

    top_pad, right_pad, bottom_pad, left_pad = req.padding_px
    tf.text_frame_format.margin_top = _px_to_pt(top_pad, canvas_h_px, slide_h_pt)
    tf.text_frame_format.margin_right = _px_to_pt(right_pad, canvas_w_px, slide_w_pt)
    tf.text_frame_format.margin_bottom = _px_to_pt(bottom_pad, canvas_h_px, slide_h_pt)
    tf.text_frame_format.margin_left = _px_to_pt(left_pad, canvas_w_px, slide_w_pt)

    # Strip the default placeholder paragraph Aspose seeds in every text frame.
    while tf.paragraphs.count > 0:
        tf.paragraphs.remove_at(0)

    for para_model in req.paragraphs:
        para = _build_paragraph(para_model, canvas_h_px, slide_h_pt)
        tf.paragraphs.add(para)

    return slide.shapes.index_of(shape)


_ALIGN_MAP = {
    "left": slides.TextAlignment.LEFT,
    "center": slides.TextAlignment.CENTER,
    "right": slides.TextAlignment.RIGHT,
    "justify": slides.TextAlignment.JUSTIFY,
}


def _build_paragraph(model: ParagraphModel, canvas_h_px: float, slide_h_pt: float) -> slides.Paragraph:
    para = slides.Paragraph()
    para.paragraph_format.alignment = _ALIGN_MAP.get(model.align, slides.TextAlignment.LEFT)
    # line_height is a multiplier; Aspose's space_within is a percent.
    para.paragraph_format.space_within = float(model.line_height) * 100.0

    for run in model.runs:
        portion = _build_portion(run, canvas_h_px, slide_h_pt)
        para.portions.add(portion)
    return para


def _build_portion(run: TextRunModel, canvas_h_px: float, slide_h_pt: float) -> slides.Portion:
    portion = slides.Portion()
    portion.text = run.text
    pf = portion.portion_format
    pf.font_bold = slides.NullableBool.TRUE if run.bold else slides.NullableBool.FALSE
    pf.font_italic = slides.NullableBool.TRUE if run.italic else slides.NullableBool.FALSE
    pf.font_underline = slides.TextUnderlineType.SINGLE if run.underline else slides.TextUnderlineType.NONE
    # CSS px font height → pt via slide-height ratio.
    pf.font_height = _px_to_pt(run.font_size_px, canvas_h_px, slide_h_pt)
    if run.font_family:
        pf.latin_font = slides.FontData(run.font_family)
    pf.fill_format.fill_type = slides.FillType.SOLID
    pf.fill_format.solid_fill_color.color = _hex_to_color(run.color)
    return portion


def add_image_shape(
    pres: slides.Presentation,
    slide_index: int,
    req: ImageShapeRequest,
    canvas_w_px: float,
    canvas_h_px: float,
) -> int:
    slide = pres.slides[slide_index]
    slide_w_pt = float(pres.slide_size.size.width)
    slide_h_pt = float(pres.slide_size.size.height)

    x, y, w, h = _bbox_to_pt(req.bbox, canvas_w_px, canvas_h_px, slide_w_pt, slide_h_pt)
    img_bytes = base64.b64decode(req.image_base64)
    image = pres.images.add_image(io.BytesIO(img_bytes))
    pic = slide.shapes.add_picture_frame(slides.ShapeType.RECTANGLE, x, y, w, h, image)
    pic.line_format.fill_format.fill_type = slides.FillType.NO_FILL
    return slide.shapes.index_of(pic)


def add_table_shape(
    pres: slides.Presentation,
    slide_index: int,
    req: TableShapeRequest,
    canvas_w_px: float,
    canvas_h_px: float,
) -> int:
    slide = pres.slides[slide_index]
    slide_w_pt = float(pres.slide_size.size.width)
    slide_h_pt = float(pres.slide_size.size.height)

    if not req.cells or not req.cells[0]:
        raise ValueError("table must have at least one row with one cell")

    rows = len(req.cells)
    cols = len(req.cells[0])
    x, y, w, h = _bbox_to_pt(req.bbox, canvas_w_px, canvas_h_px, slide_w_pt, slide_h_pt)
    col_widths = _equal_split(w, cols)
    row_heights = _equal_split(h, rows)
    table = slide.shapes.add_table(x, y, col_widths, row_heights)

    for r, row in enumerate(req.cells):
        for c, cell_para in enumerate(row[:cols]):
            cell = table.rows[r][c]
            tf = cell.text_frame
            while tf.paragraphs.count > 0:
                tf.paragraphs.remove_at(0)
            tf.paragraphs.add(_build_paragraph(cell_para, canvas_h_px, slide_h_pt))

    return slide.shapes.index_of(table)


def _equal_split(total: float, n: int) -> list[float]:
    return [total / n] * n


def add_svg_shape(
    pres: slides.Presentation,
    slide_index: int,
    req: SvgShapeRequest,
    canvas_w_px: float,
    canvas_h_px: float,
) -> int:
    """Add an SVG as a native vector picture frame (Aspose decodes it to
    a MetaShape; stays editable + crisp at any zoom)."""
    slide = pres.slides[slide_index]
    slide_w_pt = float(pres.slide_size.size.width)
    slide_h_pt = float(pres.slide_size.size.height)

    x, y, w, h = _bbox_to_pt(req.bbox, canvas_w_px, canvas_h_px, slide_w_pt, slide_h_pt)
    svg_image = pres.images.add_image(req.svg.encode("utf-8"))
    pic = slide.shapes.add_picture_frame(slides.ShapeType.RECTANGLE, x, y, w, h, svg_image)
    pic.line_format.fill_format.fill_type = slides.FillType.NO_FILL
    return slide.shapes.index_of(pic)


_CHART_TYPE_MAP = {
    "bar": slides.charts.ChartType.CLUSTERED_COLUMN,
    "line": slides.charts.ChartType.LINE,
    "pie": slides.charts.ChartType.PIE,
    "doughnut": slides.charts.ChartType.DOUGHNUT,
    "area": slides.charts.ChartType.AREA,
}


def add_chart_shape(
    pres: slides.Presentation,
    slide_index: int,
    req: ChartShapeRequest,
    canvas_w_px: float,
    canvas_h_px: float,
) -> int:
    """Build a native PPTX chart from a Chart.js-shaped config — series
    data lands in the chart's worksheet so PowerPoint's right-click Edit
    Data flow works."""
    slide = pres.slides[slide_index]
    slide_w_pt = float(pres.slide_size.size.width)
    slide_h_pt = float(pres.slide_size.size.height)

    x, y, w, h = _bbox_to_pt(req.bbox, canvas_w_px, canvas_h_px, slide_w_pt, slide_h_pt)
    chart_type = _CHART_TYPE_MAP.get(req.type, slides.charts.ChartType.CLUSTERED_COLUMN)
    chart = slide.shapes.add_chart(chart_type, x, y, w, h)

    wb = chart.chart_data.chart_data_workbook
    # Wipe the default sample data Aspose seeds (2 series × 4 categories).
    chart.chart_data.series.clear()
    chart.chart_data.categories.clear()

    # Categories (labels) in column A.
    for i, label in enumerate(req.labels):
        chart.chart_data.categories.add(wb.get_cell(0, i + 1, 0, str(label)))

    # Each chart family takes a different add_data_point method on Aspose's
    # Python bindings — dispatch by type so line/pie don't 500.
    add_dp = {
        "bar": lambda s, cell: s.data_points.add_data_point_for_bar_series(cell),
        "line": lambda s, cell: s.data_points.add_data_point_for_line_series(cell),
        "pie": lambda s, cell: s.data_points.add_data_point_for_pie_series(cell),
        "doughnut": lambda s, cell: s.data_points.add_data_point_for_pie_series(cell),
        "area": lambda s, cell: s.data_points.add_data_point_for_area_series(cell),
    }[req.type]

    # One series per dataset. Series labels in row 0; values down each column.
    for col, ds in enumerate(req.datasets, start=1):
        series_cell = wb.get_cell(0, 0, col, ds.label or f"Series {col}")
        series = chart.chart_data.series.add(series_cell, chart_type)
        for row, value in enumerate(ds.data, start=1):
            data_cell = wb.get_cell(0, row, col, float(value))
            add_dp(series, data_cell)
        if ds.color:
            series.format.fill.fill_type = slides.FillType.SOLID
            series.format.fill.solid_fill_color.color = _hex_to_color(ds.color)
            if req.type in ("line", "area"):
                series.format.line.fill_format.fill_type = slides.FillType.SOLID
                series.format.line.fill_format.solid_fill_color.color = _hex_to_color(ds.color)

    chart.has_title = bool(req.title)
    if req.title:
        chart.chart_title.add_text_frame_for_overriding(req.title)

    # Hide the legend for single-series charts to match Chart.js default
    # when legend.display=false (most fixtures).
    if len(req.datasets) <= 1:
        chart.has_legend = False

    return slide.shapes.index_of(chart)


def save_presentation_bytes(pres: slides.Presentation) -> bytes:
    """Serialize the presentation to PPTX bytes."""
    stream = io.BytesIO()
    pres.save(stream, slides.export.SaveFormat.PPTX)
    return stream.getvalue()
