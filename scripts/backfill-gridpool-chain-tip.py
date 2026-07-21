#!/usr/bin/env python3
"""Backfill GridPool chain-tip correlation into locally stored race JSON."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

import str_race  # noqa: E402


async def enrich(path: Path, gridpool_url: str) -> bool:
    data = json.loads(path.read_text())
    first_epoch = float(data["first_epoch"])
    arrivals = {
        pool: float(offset_ms) / 1000.0
        for pool, offset_ms in data.get("arrivals_offset_ms", {}).items()
    }
    race = SimpleNamespace(
        prevhash=data["prevhash"],
        first_epoch=first_epoch,
        first_ts=0.0,
        arrivals=arrivals,
    )
    correlation = await str_race._gridpool_tip_correlation(
        race,
        gridpool_url,
        attempts=1,
    )
    if not correlation.get("available"):
        return False
    data["gridpool_chain_tip"] = correlation
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)
    return True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--races-dir", required=True, type=Path)
    parser.add_argument("--gridpool-url", required=True)
    args = parser.parse_args()

    paths = sorted(
        (path for path in args.races_dir.rglob("*.json") if not path.name.startswith("_")),
        reverse=True,
    )
    updated = 0
    unavailable = 0
    for path in paths:
        try:
            if await enrich(path, args.gridpool_url):
                updated += 1
            else:
                unavailable += 1
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
    print(f"updated={updated} unavailable={unavailable} total={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
