#!/usr/bin/env python3
"""Generate ERC-721 metadata JSON files for RSE Seat tokens #1–100."""

import json
import sys
from pathlib import Path

METADATA_DIR = Path(__file__).parent / "metadata"

IMAGE_URL = "https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/RSE.png"
EXTERNAL_URL = "https://theservicesexchange.com"
DESCRIPTION = (
    "A permanent provider seat on the Robot Services Exchange. "
    "Grants the holder access to /grab_job on rse-api.com. "
    "Seat is valid unless revoked for abuse."
)

ATTRIBUTES = [
    {"trait_type": "Seat Type", "value": "Golden"},
    {"trait_type": "Duration", "value": "Permanent"},
    {"trait_type": "Rate Limit", "value": "15 minutes"},
]


def build_metadata(token_id: int) -> dict:
    return {
        "name": f"RSE Golden Seat #{token_id}",
        "description": DESCRIPTION,
        "image": IMAGE_URL,
        "external_url": EXTERNAL_URL,
        "attributes": ATTRIBUTES,
    }


def main(start: int = 1, end: int = 100):
    METADATA_DIR.mkdir(exist_ok=True)

    written = 0
    errors = []

    for token_id in range(start, end + 1):
        path = METADATA_DIR / f"{token_id}.json"
        data = build_metadata(token_id)
        raw = json.dumps(data, indent=2)

        # Write
        path.write_text(raw)

        # Validate round-trip
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"#{token_id}: {exc}")
            continue

        written += 1

    if errors:
        for e in errors:
            print(f"ERROR {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Generated {written} metadata files in {METADATA_DIR}/")
    print(f"  First: {METADATA_DIR}/1.json")
    print(f"  Last:  {METADATA_DIR}/{end}.json")


if __name__ == "__main__":
    main()
