"""Default subtitle basenames from untrusted video titles."""
from datetime import datetime
from pathlib import PureWindowsPath
import re


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def link_subtitle_stem(title: object, *, timestamp: float | None = None) -> str:
    if isinstance(title, str):
        cleaned = _UNSAFE.sub("_", " ".join(title.split())).strip(" ._")[:80].rstrip(" .")
        if cleaned and not PureWindowsPath(cleaned).is_reserved():
            return cleaned
    local_time = datetime.now() if timestamp is None else datetime.fromtimestamp(timestamp)
    return local_time.strftime("%Y-%m-%d_%H-%M-%S")
