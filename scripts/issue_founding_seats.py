#!/usr/bin/env python3
"""Issue founding seats 1-1000 (Dr. Aftab) and 1001-11000 (Amanda Jean)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seats import FOUNDING_TRANCHES, issue_founding_seats, write_owner_export

EXPORT_DIR = ROOT / "seat_admin" / "exports"


def main() -> int:
    result = issue_founding_seats()
    print(
        f"issued={result['issued']} skipped={result['skipped']} failed={result['failed']}"
    )
    for tranche, (_, _, owner) in zip(result["tranches"], FOUNDING_TRANCHES):
        print(
            f"  {owner}: {tranche['start']}-{tranche['end']} "
            f"wrote={tranche['issued']} skipped={tranche['skipped']} failed={tranche['failed']}"
        )
        slug = owner.lower().replace(" ", "_").replace(".", "")
        write_owner_export(EXPORT_DIR / f"{slug}.jsonl", tranche["seats"])
        print(f"  export: seat_admin/exports/{slug}.jsonl ({len(tranche['seats'])} new phrases)")
    if result["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
