"""Version import and package health."""

from __future__ import annotations

import layoutpatch


def test_version_is_string() -> None:
    assert isinstance(layoutpatch.__version__, str)
    assert layoutpatch.__version__ == "0.1.0"
