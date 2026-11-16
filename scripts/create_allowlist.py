#!/usr/bin/env python3
"""Create a Bedrock allowlist at runtime from a GitHub Actions secret."""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: create_allowlist.py OUTPUT_PATH", file=sys.stderr)
        return 2

    gamertag = os.environ.get("MINECRAFT_GAMERTAG", "").strip()
    if not gamertag:
        print("MINECRAFT_GAMERTAG is missing.", file=sys.stderr)
        return 1

    output_path = Path(sys.argv[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    allowlist = [
        {
            "ignoresPlayerLimit": False,
            "name": gamertag,
        }
    ]
    output_path.write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
