#!/usr/bin/env python3
"""Create a content-opaque copy and hash manifest of Codex rollout JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path):
    for folder in ("sessions", "archived_sessions"):
        base = root / folder
        if base.is_dir():
            for path in sorted(base.rglob("*.jsonl")):
                if path.is_file():
                    yield path, path.relative_to(root)


def _existing_ancestor(path: Path) -> Path:
    candidate = path.resolve(strict=False)
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise FileNotFoundError(f"no existing ancestor for destination: {path}")
        candidate = parent
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")),
    )
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit("destination already exists; refusing to overwrite")
    selected = list(_files(args.source_root))
    required = sum(path.stat().st_size for path, _ in selected)
    available = shutil.disk_usage(_existing_ancestor(args.destination.parent)).free
    summary = {"files": len(selected), "bytes": required, "free_bytes": available}
    if args.dry_run:
        print(json.dumps({**summary, "dry_run": True}, sort_keys=True))
        return 0
    if available < required * 2:
        raise SystemExit("insufficient free space: require at least twice the source bytes")
    args.destination.mkdir(parents=True, mode=0o700)
    records = []
    unstable = 0
    for source, relative in selected:
        before = source.stat()
        target = args.destination / "data" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        after = source.stat()
        changed = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
        unstable += int(changed)
        records.append(
            {
                "path_id": hashlib.sha256(relative.as_posix().encode()).hexdigest(),
                "relative_path": relative.as_posix(),
                "bytes": target.stat().st_size,
                "sha256": _hash_file(target),
                "source_changed_during_copy": changed,
            }
        )
    manifest = {
        "format": 1,
        "source_system": "codex",
        "source_instance": "main-windows",
        "files": records,
        "summary": {**summary, "source_changed_during_copy": unstable},
    }
    (args.destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({**summary, "unstable_files": unstable, "snapshot_created": True}))
    return 2 if unstable else 0


if __name__ == "__main__":
    raise SystemExit(main())
