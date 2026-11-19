import mimetypes
import os
from typing import Optional


def sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = name.replace("\x00", "").replace("/", "").replace("\\", "")
    if len(name) > 200:
        stem, ext = os.path.splitext(name)
        name = stem[: 200 - len(ext)] + ext
    return name or "unnamed"


def get_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def guess_mime_type(filename: str) -> Optional[str]:
    mime, _ = mimetypes.guess_type(filename)
    return mime
