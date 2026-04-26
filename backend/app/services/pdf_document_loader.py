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
