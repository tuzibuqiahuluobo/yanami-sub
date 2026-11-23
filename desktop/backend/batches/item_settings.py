"""Rules for fields that belong to one input rather than a whole batch."""
from pathlib import Path


def new_item_values(source: str) -> dict:
    return {
        "input": source.strip(), "output": None, "name": "", "group": "", "priority": 0,
        "llm_video": None, "refined_srt": None, "link_format": None, "programme_reference": None,
    }


def validate_item_materials(items) -> None:
    """Do not execute legacy manifests that accidentally broadcast one file."""
    for field, label in (("llm_video", "补充视频 / supplemental video"),
                         ("refined_srt", "人工精修字幕 / refined subtitles")):
        seen = {}
        for index, item in enumerate(items, 1):
            if item.stage not in {"translated-srt", "final-srt"} or not (value := getattr(item, field)):
                continue
            path = str(Path(value).expanduser().resolve()).casefold()
            if path in seen:
                raise ValueError(
                    f"批次第 {seen[path]} 和 {index} 项使用了同一份{label}。请逐项选择对应素材。"
                    f" / Items {seen[path]} and {index} share a per-item file; select the matching file for each."
                )
            seen[path] = index
