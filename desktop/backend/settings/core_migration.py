"""Review and explicitly confirmed conversion of the safe legacy media settings."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import tomllib
import uuid

from desktop.backend.common.core_compat import unified_llm_contract
from desktop.backend.settings.config_file import (
    _ARRAY_TABLE_RE, _MULTILINE_MARKERS, _VALUE_RE, _key_line_re, _lock_path, _table_spans,
)


def check_config_migration(path):
    if not unified_llm_contract():
        return
    from finesub.config import read_config
    from finesub.llm.routing.model_catalog import default_model_catalog
    from finesub.llm.routing.model_routes import load_model_routes

    data = read_config(path)
    llm = data.get("llm", {})
    if not isinstance(llm, dict):
        raise ValueError("[llm] 必须是配置表 / llm must be a table")
    retired = sorted(set(llm) & {"planning_media", "correction_media"})
    if retired:
        raise ValueError(
            "旧配置需要审阅，原文件未修改：" + ", ".join(retired) +
            "。纠错媒体请明确改用 [llm] media；规划阶段已移除，不会自动改绑模型。"
            " / Review legacy media configuration before running")
    # Core owns catalog/preset/binding validation; do not guess replacement
    # models, copy old WorkBuddy credentials, or enable CodeBuddy credits.
    load_model_routes(user_config=llm, catalog=default_model_catalog())


def _media_text(original: str, llm: dict) -> tuple[str, list[str]]:
    from finesub.llm.routing.profiles import MEDIA

    retired = set(llm) & {"planning_media", "correction_media"}
    if not retired:
        return original, []
    for name in retired | ({"media"} if "media" in llm else set()):
        if not isinstance(llm[name], str) or llm[name] not in MEDIA:
            raise ValueError(f"{name} 无法安全转换，请人工审阅 / Invalid media setting")
    media = llm.get("media", llm.get("correction_media"))
    if media is None:
        raise ValueError("只有规划媒体配置，无法推断纠错媒体；请先明确 [llm] media / Set media explicitly")
    if "media" in llm and llm.get("correction_media", media) != media:
        raise ValueError("media 与 correction_media 冲突，请人工选择 / Conflicting media choices")
    if any(marker in original for marker in _MULTILINE_MARKERS) or any(
        _ARRAY_TABLE_RE.match(line) for line in original.splitlines()
    ):
        raise ValueError("多行字符串或数组配置需人工审阅，未修改原文件 / Complex TOML requires manual review")
    lines = original.splitlines(keepends=True)
    span = _table_spans(original.splitlines()).get("llm")
    if span is None:
        raise ValueError("无法安全定位 [llm]，请人工审阅 / Cannot locate a simple llm table")
    changes = []
    for key in sorted(retired):
        found = False
        for index in range(span[0] + 1, span[1]):
            match = _key_line_re(key).match(lines[index])
            if not match:
                continue
            found = True
            if key == "correction_media" and "media" not in llm:
                start = len(match.group(1))
                lines[index] = lines[index][:start] + "media" + lines[index][start + len(key):]
                changes.append(f"correction_media → media = {media}")
            else:
                indent, _equals, rest = match.groups()
                value = _VALUE_RE.match(rest)
                trailing = rest[value.end():].rstrip("\r\n") if value else ""
                ending = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
                lines[index] = indent + trailing.lstrip() + ending if trailing.strip().startswith("#") else ""
                changes.append(f"移除 / Remove {key} = {llm[key]}")
            break
        if not found:
            raise ValueError(f"{key} 的写法需人工审阅 / Setting cannot be edited safely")
    candidate = "".join(lines)
    new_llm = tomllib.loads(candidate).get("llm", {})
    if new_llm.get("media") != media or any(key in new_llm for key in retired):
        raise ValueError("转换校验失败，未修改配置 / Media conversion validation failed")
    return candidate, changes


def _plan(path: Path):
    public = {"status": "legacy", "config_path": str(path), "changes": [], "issues": [], "token": ""}
    if not unified_llm_contract():
        return public, {}, b""
    from finesub.paths import resolve_model_catalog_override
    from finesub.llm.routing.model_catalog import load_model_catalog, merge_catalogs
    from finesub.llm.routing.model_routes import load_model_routes
    from desktop.backend.knowledge.backup import _not_link

    files = {}
    try:
        original = b""
        if path.exists():
            _not_link(path)
            original = path.read_bytes()
            files["config.toml"] = (path, original)
        data = tomllib.loads(original.decode("utf-8"))
        llm = data.get("llm", {})
        if not isinstance(llm, dict):
            raise ValueError("[llm] must be a table")
        candidate, changes = _media_text(original.decode("utf-8"), llm)
        public["changes"] = changes
        catalog = load_model_catalog()
        override = resolve_model_catalog_override()
        if override is not None:
            _not_link(override)
            contents = override.read_bytes()
            files["model_catalog.psv"] = (override, contents)
            catalog = merge_catalogs(catalog, load_model_catalog(override, self_reported=True))
        load_model_routes(user_config=tomllib.loads(candidate).get("llm", {}), catalog=catalog)
        if any(source.read_bytes() != contents for source, contents in files.values()):
            raise ValueError("预览期间配置已变化，请重新预览 / Config changed during preview")
        identity = {name: [str(source), hashlib.sha256(contents).hexdigest()] for name, (source, contents) in files.items()}
        identity["candidate"] = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
        return {**public, "status": "ready" if changes else "current", "token": token if changes else ""}, files, candidate.encode("utf-8")
    except (OSError, ValueError, RuntimeError) as error:
        return {**public, "status": "blocked", "issues": [str(error)]}, files, b""


def preview_config_migration(path: Path) -> dict:
    return _plan(path)[0]


def apply_config_migration(path: Path, token: str, *, confirmed: bool = False) -> dict:
    from finesub_bootstrap.fsops import write_atomic
    from finesub_bootstrap.locks import holding_lock
    from desktop.backend.knowledge.backup import _not_link

    if confirmed is not True or not isinstance(token, str) or len(token) != 64:
        raise ValueError("请先预览并明确确认 / Preview and explicit confirmation required")
    with holding_lock(_lock_path(path), timeout=10):
        plan, files, candidate = _plan(path)
        if plan["status"] != "ready" or plan["token"] != token:
            raise ValueError("配置或模型目录已变化，或仍需人工审阅；请重新预览 / Preview is stale or blocked")
        backups = path.parent / "config-backups"
        backups.mkdir(parents=True, exist_ok=True)
        _not_link(backups)
        final = backups / ("media-v1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex)
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=backups) as temporary:
            stage = Path(temporary)
            records = {}
            for name, (source, contents) in files.items():
                with (stage / name).open("xb") as stream:
                    stream.write(contents)
                    stream.flush()
                    os.fsync(stream.fileno())
                digest = hashlib.sha256(contents).hexdigest()
                if hashlib.sha256((stage / name).read_bytes()).hexdigest() != digest:
                    raise RuntimeError("配置备份校验失败 / Config backup verification failed")
                records[name] = {"source": str(source), "sha256": digest}
            receipt = {"format": "yanami-config-media-v1", "files": records, "preview_token": token,
                       "candidate_sha256": hashlib.sha256(candidate).hexdigest()}
            write_atomic(stage / "manifest.json", json.dumps(receipt, ensure_ascii=False, indent=2))
            if json.loads((stage / "manifest.json").read_text(encoding="utf-8")) != receipt:
                raise RuntimeError("配置备份清单无效 / Invalid config backup receipt")
            os.replace(stage, final)
        # Human editors need not honor our lock. Re-read after the backup too.
        if any(source.read_bytes() != contents for source, contents in files.values()):
            raise ValueError(f"配置已变化，未覆盖；备份保留 / Config changed; backup: {final}")
        write_atomic(path, candidate.decode("utf-8"), newline="")
        if path.read_bytes() != candidate:
            raise RuntimeError(f"配置写入后已变化，请核查；不覆盖当前内容 / Verify config; backup: {final}")
    from finesub.config import clear_config_cache
    from finesub.llm.routing.model_catalog import default_model_catalog
    from finesub.llm.routing.model_routes import default_model_routes
    clear_config_cache()
    default_model_catalog.cache_clear()
    default_model_routes.cache_clear()
    return {"status": "applied", "config_path": str(path), "backup_path": str(final), "changes": plan["changes"]}
