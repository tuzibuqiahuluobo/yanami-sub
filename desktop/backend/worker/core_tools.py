"""Explicit desktop actions backed by FineSub's local stores."""

import json
import sys


def run(body):
    action = body["action"]
    if action in {"glossaries", "fetch_glossary"}:
        from finesub.llm import glossary_store as store
        from finesub.paths import resolve_knowledge_root

        root = resolve_knowledge_root()
        published = store.published()
        if action == "fetch_glossary":
            if body["game"] not in {item.game for item in published}:
                raise ValueError("请选择已发布的术语表 / Select a published glossary")
            store.fetch(root, body["game"])
        installed = store.installed(root)
        return {"games": [
            {"name": item.game, "installed": item.game in installed} for item in published
        ]}
    if action in {"quota", "thaw_quota"}:
        from finesub import key_freeze
        from finesub.speech.joint import quota

        frozen, account = key_freeze.listing(), quota.today_rows()
        rows = {item.row: {"id": item.row, "until": item.until.isoformat(), "spent": True} for item in frozen}
        for row, usage in account:
            entry = rows.setdefault(row, {"id": row, "spent": bool(usage["exhausted"])})
            entry.update(seconds=usage["seconds"], calls=usage["calls"])
        if action == "thaw_quota":
            key = body["row"]
            if key not in rows or not rows[key]["spent"]:
                raise ValueError("该条目未暂停或已更新 / The selected quota entry is no longer paused")
            key_freeze.thaw([key])
            quota.clear_spent([key])
            return run({"action": "quota"})
        return {"rows": list(rows.values())}
    raise ValueError("Unknown core tool")


def main():
    try:
        result = {"ok": True, "data": run(json.loads(sys.stdin.readline()))}
    except Exception as error:
        result = {"ok": False, "error": {"message": str(error)}}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
