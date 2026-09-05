#!/usr/bin/env python3
"""Atomically rebuild a Python venv after the system Python ABI changes."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def repair_relocated_scripts(venv: Path, previous_root: Path) -> list[str]:
    """Rewrite absolute venv paths embedded before an atomic directory rename."""
    old = str(previous_root).encode()
    new = str(venv).encode()
    repaired: list[str] = []
    bin_dir = venv / "bin"
    if old == new or not bin_dir.is_dir():
        return repaired
    for path in bin_dir.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if old not in content:
            continue
        path.write_bytes(content.replace(old, new))
        repaired.append(path.name)
    return sorted(repaired)


def relocated_roots(venv: Path) -> list[Path]:
    """Find temporary build paths left in activation scripts after a rename."""
    activate = venv / "bin" / "activate"
    try:
        content = activate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    marker = f".{venv.name}.rebuild-"
    roots: set[Path] = set()
    for match in re.finditer(
        r"(?:(?:export )?VIRTUAL_ENV=|cygpath )['\"]?([^'\"\n)]+)", content
    ):
        candidate = match.group(1).strip()
        if marker in candidate and candidate != str(venv):
            roots.add(Path(candidate))
    return sorted(roots)


def probe(executable: Path, imports: list[str]) -> dict[str, object]:
    code = "\n".join(["import sys", *[f"import {name}" for name in imports], "print(sys.version.split()[0])"])
    try:
        result = subprocess.run(
            [str(executable), "-c", code], text=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"healthy": False, "python_version": "", "error": str(exc)}
    return {
        "healthy": result.returncode == 0,
        "python_version": result.stdout.strip() if result.returncode == 0 else "",
        "error": result.stderr.strip()[-1000:] if result.returncode else "",
    }


def rebuild(
    venv: Path,
    packages: list[str],
    imports: list[str],
    system_site_packages: bool = False,
) -> dict[str, object]:
    executable = venv / "bin" / "python3"
    before = probe(executable, imports)
    if before["healthy"]:
        repaired_scripts: set[str] = set()
        repaired_roots: list[str] = []
        for previous_root in relocated_roots(venv):
            repaired_scripts.update(repair_relocated_scripts(venv, previous_root))
            repaired_roots.append(str(previous_root))
        after = probe(executable, imports)
        return {
            "changed": bool(repaired_scripts),
            "venv": str(venv),
            "repaired_roots": repaired_roots,
            "repaired_scripts": sorted(repaired_scripts),
            "before": before,
            "after": after,
        }

    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    stage = venv.with_name(f".{venv.name}.rebuild-{stamp}-{os.getpid()}")
    backup = venv.with_name(f"{venv.name}.pre-python-rebuild-{stamp}")
    if stage.exists() or backup.exists():
        raise RuntimeError("unique rebuild or backup path already exists")

    create = [sys.executable, "-m", "venv"]
    if system_site_packages:
        create.append("--system-site-packages")
    create.append(str(stage))
    try:
        subprocess.run(create, check=True)
        subprocess.run(
            [str(stage / "bin" / "python3"), "-m", "pip", "install", *packages],
            check=True,
        )
        staged = probe(stage / "bin" / "python3", imports)
        if not staged["healthy"]:
            raise RuntimeError(f"staged runtime failed import probe: {staged['error']}")
        if venv.exists() or venv.is_symlink():
            venv.rename(backup)
        stage.rename(venv)
        repaired_scripts = repair_relocated_scripts(venv, stage)
        after = probe(executable, imports)
        if not after["healthy"]:
            venv.rename(stage)
            if backup.exists():
                backup.rename(venv)
            raise RuntimeError(f"installed runtime failed import probe: {after['error']}")
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    return {
        "changed": True,
        "venv": str(venv),
        "backup": str(backup) if backup.exists() else "",
        "repaired_scripts": repaired_scripts,
        "before": before,
        "after": after,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--package", action="append", required=True)
    parser.add_argument("--check-import", action="append", required=True)
    parser.add_argument("--system-site-packages", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.venv.parent.mkdir(parents=True, exist_ok=True)
    lock_path = args.venv.with_name(f".{args.venv.name}.rebuild.lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        payload = rebuild(
            args.venv,
            args.package,
            args.check_import,
            args.system_site_packages,
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
