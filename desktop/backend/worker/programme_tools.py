"""Small offline commands run by the installed Python runtime, not the launcher."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from desktop.backend.common.programme_reference import ProgrammeReference, load_alignment
from desktop.backend.common.subtitle_roles import describe_roles, export_roles, translated_rows


def run(payload: dict) -> dict:
    if payload["action"] == "preview":
        reference = ProgrammeReference.model_validate(payload["reference"])
        cues, duration_ms = load_alignment(reference, payload["reaction"])
        indices = range(len(cues)) if len(cues) <= 8 else (i * (len(cues) - 1) // 7 for i in range(8))
        return {"duration_ms": duration_ms, "count": len(cues), "sample": [
            {"start_ms": round(cue.start * 1000), "end_ms": round(cue.end * 1000), "text": cue.text[:300]}
            for cue in (cues[index] for index in indices)
        ]}
    if payload["action"] == "roles":
        output = Path(payload["output"])
        rows = translated_rows(output)
        assignment = payload.get("assignment")
        if assignment is None:
            tracks = describe_roles(rows)
            if not tracks:
                raise ValueError("没有可确认的单人轨号 / No unambiguous speaker tracks are available")
            return {"tracks": tracks, "total": len(rows)}
        if not isinstance(assignment, dict):
            raise ValueError("无效分组 / Invalid role assignment")
        return export_roles(output, rows, assignment)
    raise ValueError("Unsupported programme operation")


def main() -> int:
    try:
        result = {"ok": True, "data": run(json.loads(sys.stdin.readline()))}
        code = 0
    except (OSError, TypeError, ValueError) as error:
        result = {"ok": False, "error": {"message": str(error)}}
        code = 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
