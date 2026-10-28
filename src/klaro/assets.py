"""Content-versioned static asset URLs, so browsers may cache assets for a year."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from flask import current_app, request, url_for

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


@lru_cache(maxsize=64)
def _content_version(static_folder: str, filename: str) -> str:
    return hashlib.sha256((Path(static_folder) / filename).read_bytes()).hexdigest()[:16]


def asset_version(filename: str) -> str:
    static_folder = current_app.static_folder
    if static_folder is None:
        raise RuntimeError("The application has no static folder")
    return _content_version(static_folder, filename)


def asset_url(filename: str) -> str:
    """Return the static URL with a content hash, which changes whenever the file changes."""
    return url_for("static", filename=filename, v=asset_version(filename))


def static_cache_control() -> str:
    """Cache only requests for the current content version; anything else revalidates."""
    filename = (request.view_args or {}).get("filename")
    if not isinstance(filename, str):
        return REVALIDATE
    try:
        current = asset_version(filename)
    except OSError:
        return REVALIDATE
    return IMMUTABLE if request.args.get("v") == current else REVALIDATE
