#!/usr/bin/env python3
"""Import a private local Discord user.id to display-name CSV into the shared ledger."""

from __future__ import annotations

import argparse
import csv
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


USER_ID_RE = re.compile(r"^discord:[0-9]{5,32}$")
EXPECTED_FIELDS = ["user_id", "display_name"]
MAX_FILE_BYTES = 64 * 1024
MAX_ROWS = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and import an ignored mode-0600 CSV without printing any IDs or names."
        )
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the file but do not contact PostgreSQL",
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[tuple[str, str]]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("input path is not a regular file")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"input file exceeds {MAX_FILE_BYTES} bytes")

    if os.name == "posix":
        mode = stat.S_IMODE(resolved.stat().st_mode)
        if mode & 0o077:
            raise ValueError("input file must not be readable or writable by group/other (use mode 0600)")

    rows: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_FIELDS:
            raise ValueError("CSV header must be exactly: user_id,display_name")
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"row {row_number} has unexpected extra columns")
            user_id = (row.get("user_id") or "").strip()
            display_name = (row.get("display_name") or "").strip()
            if not USER_ID_RE.fullmatch(user_id):
                raise ValueError(f"row {row_number} has an invalid Discord user ID format")
            if not display_name or len(display_name) > 100:
                raise ValueError(f"row {row_number} display name must contain 1 to 100 characters")
            if any(ord(character) < 32 or ord(character) == 127 for character in display_name):
                raise ValueError(f"row {row_number} display name contains a control character")
            if user_id in seen_ids:
                raise ValueError(f"row {row_number} duplicates a user ID")
            if display_name in seen_names:
                raise ValueError(f"row {row_number} duplicates a display name")
            seen_ids.add(user_id)
            seen_names.add(display_name)
            rows.append((user_id, display_name))
            if len(rows) > MAX_ROWS:
                raise ValueError(f"CSV exceeds the {MAX_ROWS}-row safety limit")

    if not rows:
        raise ValueError("CSV must contain at least one mapping row")
    return rows


def build_psql_input(rows: list[tuple[str, str]]) -> str:
    normalized = io.StringIO(newline="")
    writer = csv.writer(normalized, lineterminator="\n")
    writer.writerow(EXPECTED_FIELDS)
    writer.writerows(rows)
    return """BEGIN;
CREATE TEMP TABLE incoming_hermes_user_aliases (
  user_id text,
  display_name text
);
\\copy incoming_hermes_user_aliases(user_id, display_name) FROM STDIN WITH (FORMAT csv, HEADER true)
""" + normalized.getvalue() + """\\.
INSERT INTO usage.hermes_user_aliases (user_id, display_name, updated_at)
SELECT user_id, display_name, now()
FROM incoming_hermes_user_aliases
ON CONFLICT (user_id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  updated_at = EXCLUDED.updated_at;
COMMIT;
"""


def main() -> int:
    args = parse_args()
    try:
        rows = load_rows(args.csv_path)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"Validated {len(rows)} mapping row(s); no data was written.")
        return 0

    repo_dir = Path(__file__).resolve().parents[1]
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "shared-ledger",
        "psql",
        "--username",
        "ledger_admin",
        "--dbname",
        "usage_ledger",
        "--set",
        "ON_ERROR_STOP=1",
    ]
    completed = subprocess.run(
        command,
        cwd=repo_dir,
        input=build_psql_input(rows),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        print(
            "Import failed. Database output was suppressed because it may contain private mappings.",
            file=sys.stderr,
        )
        return 1

    print(f"Imported {len(rows)} private mapping row(s) into the shared ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
