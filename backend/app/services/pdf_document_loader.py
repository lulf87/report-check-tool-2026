from pathlib import Path
from typing import Any
import re

import fitz


PHOTO_PAGE_RENDER_SCALE = 2
PHOTO_IMAGE_CROP_RENDER_SCALE = 4


class PDFDocumentLoader:
    def load(
        self,
        pdf_path: Path,
        render_dir: Path | None = None,
        render_textless_pages: bool = False,
    ) -> dict[str, Any]:
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)

        pages: list[dict[str, Any]] = []
        with fitz.open(pdf_path) as document:
            for index, page in enumerate(document, start=1):
                rect = page.rect
                text = page.get_text("text")
                page_data: dict[str, Any] = {
                    "page": index,
                    "text": text,
                    "width": rect.width,
                    "height": rect.height,
                    "layout_words": _extract_layout_words(page),
                    "drawings": _extract_drawings(page),
                }
                should_render_page = _is_photo_page_text(text) or (render_textless_pages and not text.strip())
                if render_dir is not None and should_render_page:
                    render_dir.mkdir(parents=True, exist_ok=True)
                    image_path = render_dir / f"page-{index:03d}.png"
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(PHOTO_PAGE_RENDER_SCALE, PHOTO_PAGE_RENDER_SCALE),
                        alpha=False,
                    )
                    pixmap.save(image_path)
                    page_data["image_path"] = str(image_path)
                    crop_paths = _render_image_block_crops(page, render_dir, index)
                    if crop_paths:
                        page_data["image_crop_paths"] = [str(path) for path in crop_paths]

                pages.append(
                    page_data
                )

        return {
            "file_name": pdf_path.name,
            "path": str(pdf_path),
            "page_count": len(pages),
            "pages": pages,
        }


def _extract_layout_words(page: fitz.Page) -> list[dict[str, Any]]:
    words = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        if not str(text).strip():
            continue
        words.append(
            {
                "text": str(text),
                "x0": round(float(x0), 1),
                "y0": round(float(y0), 1),
                "x1": round(float(x1), 1),
                "y1": round(float(y1), 1),
            }
        )
    return words


def _extract_drawings(page: fitz.Page) -> list[dict[str, Any]]:
    drawings = []
    for drawing in page.get_drawings():
        rect = _rect_to_dict(drawing.get("rect"))
        if rect is None:
            continue
        items = drawing.get("items", [])
        path_start, path_end = _drawing_path_endpoints(items)

        drawings.append(
            {
                "rect": rect,
                "width": _float_or_none(drawing.get("width")),
                "fill": _color_to_list(drawing.get("fill")),
                "color": _color_to_list(drawing.get("color")),
                "ops": _drawing_ops(items),
                "path_start": path_start,
                "path_end": path_end,
            }
        )
    return drawings


def _rect_to_dict(rect: Any) -> dict[str, float] | None:
    try:
        x0 = float(rect.x0)
        y0 = float(rect.y0)
        x1 = float(rect.x1)
        y1 = float(rect.y1)
    except AttributeError:
        if isinstance(rect, dict):
            try:
                x0 = float(rect["x0"])
                y0 = float(rect["y0"])
                x1 = float(rect["x1"])
                y1 = float(rect["y1"])
            except (KeyError, TypeError, ValueError):
                return None
        elif isinstance(rect, (list, tuple)) and len(rect) >= 4:
            try:
                x0 = float(rect[0])
                y0 = float(rect[1])
                x1 = float(rect[2])
                y1 = float(rect[3])
            except (TypeError, ValueError):
                return None
        else:
            return None

    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return {"x0": round(x0, 1), "y0": round(y0, 1), "x1": round(x1, 1), "y1": round(y1, 1)}


def _float_or_none(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _color_to_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    try:
        return [round(float(item), 4) for item in value]
    except (TypeError, ValueError):
        return None


def _drawing_path_endpoints(items: Any) -> tuple[dict[str, float] | None, dict[str, float] | None]:
    if not isinstance(items, list):
        return None, None
    start = None
    end = None
    for item in items:
        if not isinstance(item, (list, tuple)):
            continue
        points = [_point_to_dict(part) for part in item[1:]]
        points = [point for point in points if point is not None]
        if points and start is None:
            start = points[0]
        if points:
            end = points[-1]
    return start, end


def _point_to_dict(point: Any) -> dict[str, float] | None:
    try:
        return {"x": round(float(point.x), 1), "y": round(float(point.y), 1)}
    except AttributeError:
        return None
    except (TypeError, ValueError):
        return None


def _drawing_ops(items: Any) -> list[str]:
    ops = []
    if not isinstance(items, list):
        return ops
    for item in items:
        if isinstance(item, (list, tuple)) and item:
            ops.append(str(item[0]))
    return ops


def _is_photo_page_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    return "检验报告照片页" in normalized or "照片和说明" in normalized


def _render_image_block_crops(page: fitz.Page, render_dir: Path, page_number: int) -> list[Path]:
    crop_paths: list[Path] = []
    matrix = fitz.Matrix(PHOTO_IMAGE_CROP_RENDER_SCALE, PHOTO_IMAGE_CROP_RENDER_SCALE)
    for index, block in enumerate(page.get_text("dict").get("blocks", []), start=1):
        if block.get("type") != 1:
            continue

        bbox = fitz.Rect(block["bbox"])
        if bbox.is_empty or bbox.width < 20 or bbox.height < 20:
            continue

        crop_path = render_dir / f"page-{page_number:03d}-crop-{index:03d}.png"
        pixmap = page.get_pixmap(matrix=matrix, clip=bbox, alpha=False)
        pixmap.save(crop_path)
        crop_paths.append(crop_path)
    return crop_paths
