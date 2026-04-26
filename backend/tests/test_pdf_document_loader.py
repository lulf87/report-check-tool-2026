from pathlib import Path

import pytest

from app.services.pdf_document_loader import PDFDocumentLoader


WORKTREE_ROOT = Path(__file__).resolve().parents[2]


def test_loader_reads_sample_report_pages():
    sample = WORKTREE_ROOT / "素材/report/3940/3940.pdf"

    pages = PDFDocumentLoader().load(sample)

    assert pages["file_name"] == "3940.pdf"
    assert pages["path"] == str(sample)
    assert pages["page_count"] == len(pages["pages"])
    assert len(pages["pages"]) >= 30
    assert "国医检" in pages["pages"][0]["text"]
    assert pages["pages"][0]["page"] == 1
    assert pages["pages"][0]["width"] > 0
    assert pages["pages"][0]["height"] > 0
    assert pages["pages"][0]["layout_words"]
    assert {"text", "x0", "y0", "x1", "y1"}.issubset(pages["pages"][0]["layout_words"][0])


def test_loader_can_render_photo_pages(tmp_path):
    sample = WORKTREE_ROOT / "素材/report/3940/3940.pdf"

    report = PDFDocumentLoader().load(sample, render_dir=tmp_path)
    rendered = [page for page in report["pages"] if page.get("image_path")]

    assert rendered
    assert all(Path(page["image_path"]).exists() for page in rendered)
    assert all("照片" in page["text"] for page in rendered)


def test_loader_renders_photo_page_image_block_crops(tmp_path):
    sample = WORKTREE_ROOT / "素材/report/5332/QW2025-5332 Draft.pdf"

    report = PDFDocumentLoader().load(sample, render_dir=tmp_path)
    page_100 = next(page for page in report["pages"] if page["page"] == 100)

    assert page_100["image_crop_paths"]
    assert all(Path(path).exists() for path in page_100["image_crop_paths"])
    assert any("page-100-crop" in Path(path).name for path in page_100["image_crop_paths"])


def test_loader_raises_for_missing_file():
    missing = WORKTREE_ROOT / "素材/report/3940/missing.pdf"

    with pytest.raises(FileNotFoundError):
        PDFDocumentLoader().load(missing)
