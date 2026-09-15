"""ColPali image-path guard tests (migrated from old repo in batch M3).

说明（新手向）：ColPali 编码前必须确认每页的截图真实存在。
这两个测试验证 `resolve_page_image_path` 的两道防线：
1. page 记录里根本没写图片路径 → 报错并提示重跑 prepare；
2. 写了路径但文件不存在 → 报错并提示在本机重跑 prepare 生成页图。
都不需要 GPU，用临时文件即可验证。
"""

from __future__ import annotations

from layoutpatch.retrieval.colpali import resolve_page_image_path
from layoutpatch.schemas import PageRecord


def test_colpali_requires_materialized_page_image(tmp_path):
    page = PageRecord(doc_id="doc", page_id="doc_p0", page_index=1)
    try:
        resolve_page_image_path(page)
    except FileNotFoundError as exc:
        assert "no page_image_path" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")

    missing = PageRecord(
        doc_id="doc",
        page_id="doc_p0",
        page_index=1,
        page_image_path=str(tmp_path / "missing.jpg"),
    )
    try:
        resolve_page_image_path(missing)
    except FileNotFoundError as exc:
        assert "Missing page image" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_colpali_uses_existing_page_image(tmp_path):
    image_path = tmp_path / "page.jpg"
    image_path.write_bytes(b"placeholder")
    page = PageRecord(
        doc_id="doc",
        page_id="doc_p0",
        page_index=1,
        page_image_path=str(image_path),
    )
    assert resolve_page_image_path(page) == image_path
