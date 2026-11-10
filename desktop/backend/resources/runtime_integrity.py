"""Validate the pinned ONNX wheels' overlapping namespace without hiding damage."""
from pathlib import Path

from finesub_bootstrap import runtime_health


def check_runtime(site_packages: Path, lock: Path, *, verify_hashes: bool = False):
    report = runtime_health.check_runtime(site_packages, lock, verify_hashes=verify_hashes)
    if report is None or not verify_hashes or not report.mismatched:
        return report
    locked = runtime_health.locked_packages(lock) or {}
    names = {"onnx", "onnx-weekly"}
    if not names.issubset(locked):
        return report
    installed = runtime_health._installed_distributions(site_packages)
    invalid = {
        *report.missing_packages, *report.duplicate_distributions,
        *(name for name, _, _ in report.version_mismatches),
    }
    if names & invalid:
        return report
    # One complete wheel must match, not a per-file mix of the two versions.
    for owner in sorted(names):
        if owner in report.missing_files or owner in report.hash_mismatches:
            continue
        entries = installed.get(owner, [])
        if len(entries) != 1:
            continue
        rows = runtime_health._record_rows(entries[0][1])
        if not rows:
            continue
        owned = {path for path, _ in rows if path.startswith("onnx/")}
        shadowed = (names - {owner}).pop()
        failures = report.hash_mismatches.get(shadowed, [])
        remaining = [path for path in failures if path not in owned]
        if remaining:
            report.hash_mismatches[shadowed] = remaining
        else:
            report.hash_mismatches.pop(shadowed, None)
        break
    return report
