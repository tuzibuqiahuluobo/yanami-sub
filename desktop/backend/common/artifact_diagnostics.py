"""Small diagnostic records kept outside the scratch artifact tree."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import stat
from types import SimpleNamespace

from finesub_bootstrap.artifacts import recorded_scratch_files


TASK_DIAGNOSTICS = "task-diagnostics.log"
BATCH_DIAGNOSTICS = "batch-diagnostics.log"
_FIELDS = ("vocal_audio", "vad_json", "vad_energy_npz", "aligned_json", "stable_json",
           "diar_json", "diar_rows_json", "speaker_judge_json", "raw_srt", "translated_srt", "final_srt")


def paths_from_output(output: Path):
    base = output.with_suffix("")
    suffixes = dict(zip(_FIELDS[:-1], ("vocal.ogg", "vad.json", "vad-energy.npz",
        "aligned.json", "stable.json", "diar.json", "diar-rows.json", "speaker-judge.json",
        "raw.srt", "translated.srt"), strict=True))
    return SimpleNamespace(final_srt=output, **{
        name: base.with_name(f"{base.name}-{suffix}") for name, suffix in suffixes.items()
    })


def append_artifact_diagnostics(log: Path, paths, *, stage: str, action: str, item: int | None = None) -> bool:
    """Record sizes and artifact roles, not filenames, transcripts or configuration."""
    def size(path) -> int | None:
        try:
            if path is not None:
                info = Path(path).lstat()
                if stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400:
                    return info.st_size
        except OSError:
            pass
        return None

    try:
        if log.is_symlink() or (log.exists() and not log.is_file()):
            return False
        files = {key: size(getattr(paths, key, None)) for key in _FIELDS}
        final_srt = getattr(paths, "final_srt", None)
        scratch = [value for path in recorded_scratch_files(final_srt) if (value := size(path)) is not None] if final_srt else []
        row = {"at": datetime.now(timezone.utc).isoformat(), "action": action, "stage": stage,
               "artifact_bytes": files, "scratch_count": len(scratch), "scratch_bytes": sum(scratch)}
        if item is not None:
            row["batch_item"] = item
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except (OSError, ValueError, TypeError):
        return False
