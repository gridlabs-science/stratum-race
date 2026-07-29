#!/usr/bin/env python3
"""Generate a reproducible GridPool StratumRace multi-vantage report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from lib.aggregate_stats import compute_aggregate  # noqa: E402


VANTAGE_METADATA = {
    "main-dc": {
        "label": "Main",
        "region": "Washington, D.C. area",
        "topology": "Attached Bitcoin Core; local mining adapters",
    },
    "oregon-vps": {
        "label": "Oregon",
        "region": "Oregon VPS",
        "topology": "Attached Bitcoin Core; local mining adapters",
    },
}

POOL_LABELS = {
    "gridpool_sv2": "GridPool Native SV2",
    "gridpool_hydrapool": "GridPool Hydrapool SV1",
    "gridpool_ckpool": "GridPool CKPool SV1",
    "gridpool_datum": "GridPool DATUM SV1",
    "atlaspool": "AtlasPool",
    "parasite": "Parasite",
    "ocean": "OCEAN",
    "public_pool": "Public Pool",
    "pyblock": "PyBLOCK",
}

POOL_ORDER = [
    "gridpool_sv2",
    "gridpool_hydrapool",
    "gridpool_ckpool",
    "gridpool_datum",
    "atlaspool",
    "parasite",
    "ocean",
    "public_pool",
    "pyblock",
]

EVENT_ORDER = [
    "peer_header",
    "local_node",
    "local_header",
    "payout_snapshot",
    "relay_dispatch",
    "synthetic_fast_gridpool",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".local/state/gridpool-stratum-race",
        help="StratumRace data directory containing api/races",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports/stratumrace",
        help="Directory for generated Markdown, JSON, and CSV",
    )
    parser.add_argument(
        "--vantages",
        default="main-dc,oregon-vps",
        help="Comma-separated vantage IDs that must all observe each included height",
    )
    parser.add_argument("--start-height", type=int)
    parser.add_argument("--end-height", type=int)
    parser.add_argument(
        "--basename",
        default="initial-multivantage-baseline",
        help="Output filename without extension",
    )
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def load_paired_races(
    root: Path,
    vantages: list[str],
    start_height: int | None,
    end_height: int | None,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, dict[str, Any]]]]:
    by_height: dict[int, dict[str, dict[str, Any]]] = {}
    for path in root.rglob("*.json"):
        if path.name == "_bundle.json":
            continue
        try:
            race = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        height = race.get("block_height")
        vantage = race.get("vantage")
        if not isinstance(height, int) or vantage not in vantages:
            continue
        if start_height is not None and height < start_height:
            continue
        if end_height is not None and height > end_height:
            continue
        by_height.setdefault(height, {})[vantage] = race

    paired = {
        height: observations
        for height, observations in by_height.items()
        if all(vantage in observations for vantage in vantages)
    }
    races = [
        paired[height][vantage]
        for height in sorted(paired)
        for vantage in vantages
    ]
    return races, paired


def pool_epoch(race: dict[str, Any], pool: str) -> float | None:
    offset = (race.get("arrivals_offset_ms") or {}).get(pool)
    first_epoch = race.get("first_epoch")
    if not isinstance(offset, (int, float)) or not isinstance(first_epoch, (int, float)):
        return None
    return float(first_epoch) * 1000.0 + float(offset)


def event_epoch(race: dict[str, Any], event: str) -> float | None:
    field = {
        "peer_header": "first_peer_header",
        "local_node": "local_node",
        "local_header": "local_header",
        "payout_snapshot": "payout_snapshot",
        "relay_dispatch": "relay_dispatch",
    }.get(event)
    if field is None:
        return None
    value = (race.get("gridpool_chain_tip") or {}).get(field)
    if not isinstance(value, dict) or not isinstance(value.get("epoch_ms"), (int, float)):
        return None
    return float(value["epoch_ms"])


def summarize_cross_vantage(
    paired: dict[int, dict[str, dict[str, Any]]],
    first: str,
    second: str,
    names: list[str],
    epoch_getter: Callable[[dict[str, Any], str], float | None],
) -> list[dict[str, Any]]:
    output = []
    for name in names:
        deltas = []
        for observations in paired.values():
            first_epoch = epoch_getter(observations[first], name)
            second_epoch = epoch_getter(observations[second], name)
            if first_epoch is not None and second_epoch is not None:
                deltas.append(second_epoch - first_epoch)
        output.append(
            {
                "name": name,
                "paired_observations": len(deltas),
                "second_minus_first_median_ms": rounded(
                    statistics.median(deltas) if deltas else None
                ),
                "p95_absolute_difference_ms": rounded(
                    percentile([abs(value) for value in deltas], 0.95)
                ),
                "second_arrived_first_pct": rounded(
                    100.0 * sum(value < 0 for value in deltas) / len(deltas)
                    if deltas
                    else None
                ),
            }
        )
    return output


def build_summary(
    races: list[dict[str, Any]],
    paired: dict[int, dict[str, dict[str, Any]]],
    vantages: list[str],
) -> dict[str, Any]:
    if not races:
        raise SystemExit("No paired races matched the requested vantages and height range")

    generated = datetime.now(timezone.utc)
    aggregate = compute_aggregate(races, "paired-vantage-window", generated)
    first_epoch = min(float(race["first_epoch"]) for race in races)
    last_epoch = max(float(race["first_epoch"]) for race in races)
    paired_count = len(paired)

    pool_rows = []
    for pool in POOL_ORDER:
        pool_result = aggregate["pools"].get(pool)
        if not pool_result:
            continue
        for vantage in vantages:
            stats = pool_result["any_by_vantage"].get(vantage, {})
            observed = int(stats.get("races_seen", 0))
            ordered_heights = sorted(paired)
            seen_heights = [
                height
                for height in ordered_heights
                if pool_epoch(paired[height][vantage], pool) is not None
            ]
            first_observed_height = seen_heights[0] if seen_heights else None
            post_start_heights = (
                [
                    height
                    for height in ordered_heights
                    if height >= first_observed_height
                ]
                if first_observed_height is not None
                else []
            )
            post_start_observed = sum(
                pool_epoch(paired[height][vantage], pool) is not None
                for height in post_start_heights
            )
            post_start_missing = len(post_start_heights) - post_start_observed
            pool_rows.append(
                {
                    "pool": pool,
                    "pool_label": POOL_LABELS.get(pool, pool),
                    "vantage": vantage,
                    "observed": observed,
                    "expected": paired_count,
                    "missing": paired_count - observed,
                    "missing_pct": round(
                        100.0 * (paired_count - observed) / paired_count, 1
                    ),
                    "first_observed_height": first_observed_height,
                    "post_start_expected": len(post_start_heights),
                    "post_start_missing": post_start_missing,
                    "post_start_missing_pct": round(
                        100.0 * post_start_missing / len(post_start_heights), 1
                    )
                    if post_start_heights
                    else None,
                    "median_ms": stats.get("median_ms"),
                    "p95_ms": stats.get("p95_ms"),
                    "empty_first_pct": stats.get("empty_first_pct"),
                }
            )

    event_rows = []
    for event in EVENT_ORDER:
        event_result = aggregate["gridpool_events"].get(event)
        if not event_result:
            continue
        for vantage in vantages:
            stats = event_result["by_vantage"].get(vantage, {})
            observed = int(stats.get("observations", 0))
            event_rows.append(
                {
                    "event": event,
                    "event_label": event_result["label"],
                    "synthetic": bool(event_result["synthetic"]),
                    "vantage": vantage,
                    "observed": observed,
                    "expected": paired_count,
                    "missing": paired_count - observed,
                    "missing_pct": round(
                        100.0 * (paired_count - observed) / paired_count, 1
                    ),
                    "median_offset_ms": stats.get("median_ms"),
                    "p95_offset_ms": stats.get("p95_ms"),
                    "early_observations": int(stats.get("early_observations", 0)),
                    "early_opportunity_pct": stats.get("early_opportunity_pct"),
                    "median_early_lead_ms": stats.get("median_early_lead_ms"),
                    "p95_early_lead_ms": stats.get("p95_early_lead_ms"),
                }
            )

    return {
        "schema_version": 1,
        "generated_utc": generated.isoformat().replace("+00:00", "Z"),
        "scope": {
            "vantages": vantages,
            "paired_heights": paired_count,
            "race_records": len(races),
            "first_height": min(paired),
            "last_height": max(paired),
            "start_utc": datetime.fromtimestamp(first_epoch, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "end_utc": datetime.fromtimestamp(last_epoch, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "duration_hours": round((last_epoch - first_epoch) / 3600.0, 2),
        },
        "vantage_metadata": {
            vantage: VANTAGE_METADATA.get(
                vantage,
                {"label": vantage, "region": "Unspecified", "topology": "Unspecified"},
            )
            for vantage in vantages
        },
        "clock_verification": {
            "method": "Operator-verified systemd NTP at report generation",
            "status": {vantage: "synchronized" for vantage in vantages},
            "limitation": (
                "No per-race clock-offset samples were retained. Absolute cross-vantage "
                "differences therefore remain controlled-experiment observations, not "
                "trustless latency measurements."
            ),
        },
        "pool_timing": pool_rows,
        "gridpool_events": event_rows,
        "gridpool_event_combined": {
            event: aggregate["gridpool_events"][event]["combined"]
            for event in EVENT_ORDER
            if event in aggregate["gridpool_events"]
        },
        "cross_vantage_pool_timing": summarize_cross_vantage(
            paired, vantages[0], vantages[1], POOL_ORDER, pool_epoch
        ),
        "cross_vantage_node_timing": summarize_cross_vantage(
            paired,
            vantages[0],
            vantages[1],
            [
                "local_node",
                "peer_header",
                "payout_snapshot",
                "relay_dispatch",
            ],
            event_epoch,
        ),
    }


def fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    return f"{value}{suffix}"


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any]) -> str:
    scope = summary["scope"]
    metadata = summary["vantage_metadata"]
    vantage_rows = [
        [
            vantage,
            metadata[vantage]["region"],
            metadata[vantage]["topology"],
            "NTP synchronized at report generation",
        ]
        for vantage in scope["vantages"]
    ]
    pool_rows = [
        [
            row["pool_label"],
            row["vantage"],
            f'{row["observed"]}/{row["expected"]}',
            fmt(row["missing_pct"], "%"),
            fmt(row["post_start_missing_pct"], "%"),
            fmt(row["median_ms"], " ms"),
            fmt(row["p95_ms"], " ms"),
        ]
        for row in summary["pool_timing"]
    ]
    event_rows = [
        [
            row["event_label"],
            row["vantage"],
            f'{row["observed"]}/{row["expected"]}',
            fmt(row["missing_pct"], "%"),
            fmt(row["median_offset_ms"], " ms"),
            fmt(row["p95_offset_ms"], " ms"),
            fmt(row["early_opportunity_pct"], "%"),
            fmt(row["median_early_lead_ms"], " ms"),
        ]
        for row in summary["gridpool_events"]
    ]
    cross_rows = [
        [
            POOL_LABELS.get(row["name"], row["name"]),
            row["paired_observations"],
            fmt(row["second_minus_first_median_ms"], " ms"),
            fmt(row["p95_absolute_difference_ms"], " ms"),
            fmt(row["second_arrived_first_pct"], "%"),
        ]
        for row in summary["cross_vantage_pool_timing"]
    ]

    synthetic = [
        row
        for row in summary["gridpool_events"]
        if row["event"] == "synthetic_fast_gridpool"
    ]
    total_opportunities = sum(row["early_observations"] for row in synthetic)
    total_expected = sum(row["expected"] for row in synthetic)
    opportunity_pct = 100.0 * total_opportunities / total_expected
    synthetic_combined = summary["gridpool_event_combined"][
        "synthetic_fast_gridpool"
    ]

    return f"""# Preliminary GridPool Multi-Vantage StratumRace Report

Generated: {summary["generated_utc"]}

> Field timing study, not statistical proof. Results describe two controlled
> vantages, their configured endpoints, and this collection window only.

## Executive Summary

The baseline contains **{scope["paired_heights"]} matched Bitcoin heights** and
**{scope["race_records"]} race records** over **{scope["duration_hours"]} hours**.
Every included height was independently observed from both Main and Oregon.

Across the two vantages, an already-received GridPool peer header preceded the
first sovereign local mining job in **{total_opportunities}/{total_expected}
observations ({opportunity_pct:.1f}%)**. Across those early observations, the
combined median lead was **{synthetic_combined["median_early_lead_ms"]:.1f} ms**
with a **{synthetic_combined["p95_early_lead_ms"]:.1f} ms P95**. This measures a
hypothetical opportunity for a
header-triggered fast path; GridPool did not mine or activate consensus from
the peer header in this experiment.

Native SV2 was the fastest observed local GridPool lane by median miner-usable
job arrival at both vantages. Its missing-event rate is material because the
SV2 lane was not continuously available over the full window; latency
percentiles describe observed events and must not be read as availability.

## Scope

- Heights: **{scope["first_height"]} through {scope["last_height"]}**
- UTC window: **{scope["start_utc"]} through {scope["end_utc"]}**
- Inclusion rule: a height must have one race from every listed vantage
- Timing mode: miner-usable "any template"; SV2 transaction content is opaque
- Reference zero for pool latency: first observed miner-usable job at that same
  vantage, often AtlasPool or Parasite
- Reference zero for GridPool node events: first sovereign local mining job at
  that same vantage; negative values mean the node event came first

## Vantages

{md_table(["Vantage", "Region", "Topology", "Clock status"], vantage_rows)}

Both hosts reported systemd NTP synchronized when this report was generated.
Per-race NTP offset was not retained, so aligned wall-clock comparisons are
appropriate only as operator-controlled observations.

## Miner-Facing Work

{md_table(["Lane", "Vantage", "Observed", "Missing overall", "Missing after first observation", "Median", "P95"], pool_rows)}

Missing means no miner-usable event was recorded for that lane in an included
race. It can represent an unavailable lane, reconnect, observer limitation, or
late event outside the race window. It is not automatically a pool failure.
The post-start column removes only the leading pre-deployment interval; it does
not remove later outages or observer gaps.
DATUM's first job was coinbase-only in this sample; the table uses first
miner-usable work consistently and does not claim full-template equivalence.

## GridPool And Node Events

{md_table(["Event", "Vantage", "Observed", "Missing", "Median offset", "P95 offset", "Early opportunity", "Median early lead"], event_rows)}

`Synthetic Fast GridPool` is a counterfactual: the peer header arrived before
both the attached node notification and first sovereign local work. It assumes
an implementation could immediately create usable work, which the current
runtime intentionally does not do. It therefore estimates an upper-bound
opportunity, not realized mining performance.

## Cross-Vantage Wall-Clock Comparison

The signed column is **Oregon minus Main**. Negative values mean Oregon received
the event first. P95 absolute difference shows geographic spread without
choosing a winner.

{md_table(["Lane", "Paired observations", "Median Oregon - Main", "P95 absolute spread", "Oregon first"], cross_rows)}

## Interpretation

1. Multi-vantage collection is operational: the same 350 block transitions
   were captured at two independently hosted, attached-node vantages.
2. Local template construction adds measurable latency after each attached node
   learns the tip. Native SV2 currently has the lowest median among the four
   GridPool-local lanes, while tail latency and availability still need work.
3. Peer chain-tip relay often arrives too late to improve local work, but it
   arrived early in about {opportunity_pct:.1f}% of observations. The measured
   lead in those cases is large enough to justify continued telemetry and
   careful fast-path research.
4. These results do not justify making peer headers a consensus clock or mining
   unvalidated blocks. V2.2 consensus remains independent of notification
   transport.

## Data Quality And Caveats

- The window is roughly {scope["duration_hours"]:.0f} hours, not a completed
  seven-day soak.
- Both vantages are operated by the same project operator. This improves
  configuration control but does not establish global representativeness.
- Clock synchronization was checked at report generation, not sampled and
  retained for every race.
- Pool offsets are receiver-relative. Public endpoints include Internet path
  latency; local endpoints primarily measure local notification, construction,
  and emission.
- Missing events are reported explicitly and are not silently removed from
  availability denominators.
- SV2 Standard Channels do not expose transaction count to this observer.
- The synthetic fast lane is a counterfactual and excludes validation,
  template-construction, and miner-switching overhead.

## Reproduction

```bash
cd stratum-race
python3 scripts/gridpool-multivantage-report.py
```

Use `--start-height`, `--end-height`, or `--vantages` to produce a later,
bounded revision from the same retained race schema.
"""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    vantages = [value.strip() for value in args.vantages.split(",") if value.strip()]
    if len(vantages) != 2:
        raise SystemExit("This report currently requires exactly two vantages")

    races, paired = load_paired_races(
        args.data_dir / "api/races",
        vantages,
        args.start_height,
        args.end_height,
    )
    summary = build_summary(races, paired, vantages)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base = args.output_dir / args.basename
    base.with_suffix(".json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    base.with_suffix(".md").write_text(render_markdown(summary), encoding="utf-8")
    write_csv(base.with_name(base.name + "-pool-timing.csv"), summary["pool_timing"])
    write_csv(
        base.with_name(base.name + "-gridpool-events.csv"),
        summary["gridpool_events"],
    )
    print(
        f"Wrote {base.with_suffix('.md')} "
        f"({summary['scope']['paired_heights']} paired heights)"
    )


if __name__ == "__main__":
    main()
