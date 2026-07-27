"""Pure statistics for StratumRace aggregates.

Extracted from the aggregate handler's computation functions
(behavior-preserving move). These functions know nothing about storage
backends — pure computation only. This is the single source of truth for
median, avg, p95, win%, empty_first%, and waste/day, for both full-template
and any-template modes.
"""

import math
import statistics
from datetime import datetime
from typing import Any, Dict, List

# Constants from the existing aggregate.py
BLOCK_INTERVAL_MS = 600_000.0
DEFAULT_FEE_FRACTION = 0.02


def new_accumulator() -> Dict[str, Any]:
    """Create a fresh statistics accumulator for a pool."""
    return {
        "offsets": [],
        "wins": 0,
        "races_seen": 0,
        "races_eligible": 0,
        "empty_first_count": 0,
        "stale_samples": [],
        "gap_samples": [],
    }


def percentile(data: List[float], pct: float) -> float:
    """Compute the given percentile using rank-based method on sorted data.

    For p95 with N items: index = ceil(0.95 * N) - 1, clamped to valid range.
    """
    ordered = sorted(data)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    idx = min(n - 1, max(0, math.ceil(pct * n) - 1))
    return ordered[idx]


def compute_stats(acc: Dict[str, Any]) -> Dict[str, Any]:
    """Compute final statistics from an accumulator.

    Returns the aggregate stat block: median_ms, avg_ms, p95_ms, wins,
    races_seen, races_eligible, win_pct, empty_first_pct, waste_min_day.
    """
    offsets = acc["offsets"]
    races_seen = acc["races_seen"]
    races_eligible = acc["races_eligible"]
    wins = acc["wins"]
    empty_first_count = acc["empty_first_count"]

    if not offsets:
        return {
            "median_ms": None,
            "avg_ms": None,
            "p95_ms": None,
            "wins": wins,
            "races_seen": races_seen,
            "races_eligible": races_eligible,
            "win_pct": None,
            "empty_first_pct": None,
            "waste_min_day": None,
        }

    median_ms = round(statistics.median(offsets), 3)
    avg_ms = round(statistics.fmean(offsets), 3)
    p95_ms = round(percentile(offsets, 0.95), 3)

    # Win percentage: wins / races_seen
    if races_seen > 0:
        win_pct = round(100.0 * wins / races_seen, 1)
        empty_first_pct = round(100.0 * empty_first_count / races_seen, 1)
    else:
        win_pct = None
        empty_first_pct = None

    # Waste per day: (avg_stale_ms + fee_fraction × avg_empty_gap_ms) / 600000 × 1440
    # Same formula as existing aggregate.py
    stale_samples = acc["stale_samples"]
    gap_samples = acc["gap_samples"]
    if stale_samples:
        stale_avg = statistics.fmean(stale_samples)
        gap_avg = statistics.fmean(gap_samples) if gap_samples else 0.0
        effective_ms = stale_avg + DEFAULT_FEE_FRACTION * gap_avg
        waste_min_day = round(effective_ms / BLOCK_INTERVAL_MS * 1440.0, 2)
    else:
        waste_min_day = None

    return {
        "median_ms": median_ms,
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "wins": wins,
        "races_seen": races_seen,
        "races_eligible": races_eligible,
        "win_pct": win_pct,
        "empty_first_pct": empty_first_pct,
        "waste_min_day": waste_min_day,
    }


GRIDPOOL_EVENT_DEFINITIONS = {
    "peer_header": {
        "label": "GridPool peer chain-tip",
        "field": "first_peer_header",
        "synthetic": False,
    },
    "local_node": {
        "label": "Local Bitcoin node notification",
        "field": "local_node",
        "synthetic": False,
    },
    "local_header": {
        "label": "Local raw block header",
        "field": "local_header",
        "synthetic": False,
    },
    "payout_snapshot": {
        "label": "GridPool payout snapshot",
        "field": "payout_snapshot",
        "synthetic": False,
    },
    "relay_dispatch": {
        "label": "GridPool relay dispatch",
        "field": "relay_dispatch",
        "synthetic": False,
    },
    "synthetic_fast_gridpool": {
        "label": "Synthetic Fast GridPool",
        "field": None,
        "synthetic": True,
    },
}


def _event_stats(offsets: List[float], eligible: int) -> Dict[str, Any]:
    """Summarize signed offsets from the first sovereign local work event."""
    early_leads = [-value for value in offsets if value < 0]
    if not offsets:
        return {
            "median_ms": None,
            "avg_ms": None,
            "p95_ms": None,
            "observations": 0,
            "races_eligible": eligible,
            "before_first_work_pct": None,
            "early_observations": 0,
            "early_opportunity_pct": 0.0 if eligible else None,
            "median_early_lead_ms": None,
            "avg_early_lead_ms": None,
            "p95_early_lead_ms": None,
        }
    ordered = sorted(offsets)
    return {
        "median_ms": round(percentile(ordered, 0.5), 3),
        "avg_ms": round(sum(ordered) / len(ordered), 3),
        "p95_ms": round(percentile(ordered, 0.95), 3),
        "observations": len(ordered),
        "races_eligible": eligible,
        "before_first_work_pct": round(
            sum(1 for value in ordered if value < 0) / len(ordered) * 100.0,
            1,
        ),
        "early_observations": len(early_leads),
        "early_opportunity_pct": round(
            len(early_leads) / eligible * 100.0,
            1,
        )
        if eligible
        else None,
        "median_early_lead_ms": round(percentile(early_leads, 0.5), 3)
        if early_leads
        else None,
        "avg_early_lead_ms": round(sum(early_leads) / len(early_leads), 3)
        if early_leads
        else None,
        "p95_early_lead_ms": round(percentile(early_leads, 0.95), 3)
        if early_leads
        else None,
    }


def _first_local_work_epoch_ms(race: Dict[str, Any], tip: Dict[str, Any]) -> float | None:
    """Find the first full SV1 or miner-usable opaque SV2 local job."""
    cohorts = race.get("pool_cohorts") or {}
    protocols = race.get("pool_protocols") or {}
    observability = race.get("template_observability") or {}
    local_pools = {name for name, cohort in cohorts.items() if cohort == "gridpool-local"}
    if not local_pools:
        return None

    race_first_epoch_ms = float(race.get("first_epoch", 0)) * 1000.0
    absolute_arrivals = tip.get("work_arrival_epoch_ms") or {}
    any_offsets = race.get("arrivals_offset_ms") or {}
    full_offsets = race.get("nonempty_arrivals_offset_ms") or {}
    arrivals: List[float] = []

    for name in local_pools:
        full_offset = full_offsets.get(name)
        if isinstance(full_offset, (int, float)):
            arrivals.append(race_first_epoch_ms + float(full_offset))
            continue

        if protocols.get(name) == "sv2" or observability.get(name) == "opaque":
            absolute = absolute_arrivals.get(name)
            if isinstance(absolute, (int, float)):
                arrivals.append(float(absolute))
                continue
            any_offset = any_offsets.get(name)
            if isinstance(any_offset, (int, float)):
                arrivals.append(race_first_epoch_ms + float(any_offset))

    return min(arrivals) if arrivals else None


def _compute_gridpool_event_stats(races: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate measured node events and the explicitly synthetic fast lane."""
    event_data: Dict[str, Dict[str, Any]] = {
        name: {
            "combined": [],
            "by_vantage": {},
            "eligible": 0,
            "eligible_by_vantage": {},
        }
        for name in GRIDPOOL_EVENT_DEFINITIONS
    }

    for race in races:
        vantage = str(race.get("vantage", "unknown"))
        tip = race.get("gridpool_chain_tip") or {}
        if not isinstance(tip, dict):
            continue
        first_local_work_epoch_ms = _first_local_work_epoch_ms(race, tip)
        if first_local_work_epoch_ms is None:
            continue

        for name, definition in GRIDPOOL_EVENT_DEFINITIONS.items():
            entry = event_data[name]
            entry["eligible"] += 1
            entry["eligible_by_vantage"][vantage] = (
                entry["eligible_by_vantage"].get(vantage, 0) + 1
            )

            event = None
            if definition["synthetic"]:
                peer = tip.get("first_peer_header")
                local_node = tip.get("local_node") or tip.get("local_zmq")
                if (
                    isinstance(peer, dict)
                    and isinstance(local_node, dict)
                    and isinstance(peer.get("epoch_ms"), (int, float))
                    and isinstance(local_node.get("epoch_ms"), (int, float))
                    and peer["epoch_ms"] < local_node["epoch_ms"]
                    and peer["epoch_ms"] < first_local_work_epoch_ms
                ):
                    event = peer
            else:
                event = tip.get(definition["field"])

            if not isinstance(event, dict):
                continue
            epoch_ms = event.get("epoch_ms")
            if not isinstance(epoch_ms, (int, float)):
                continue
            offset = float(epoch_ms) - first_local_work_epoch_ms
            entry["combined"].append(offset)
            entry["by_vantage"].setdefault(vantage, []).append(offset)

    output: Dict[str, Any] = {}
    for name, definition in GRIDPOOL_EVENT_DEFINITIONS.items():
        entry = event_data[name]
        output[name] = {
            "label": definition["label"],
            "synthetic": definition["synthetic"],
            "combined": _event_stats(entry["combined"], entry["eligible"]),
            "by_vantage": {
                vantage: _event_stats(
                    offsets,
                    entry["eligible_by_vantage"].get(vantage, 0),
                )
                for vantage, offsets in entry["by_vantage"].items()
            },
        }
    return output


def compute_aggregate(
    races: List[Dict[str, Any]], label: str, generated_at: datetime
) -> Dict[str, Any]:
    """Compute per-pool statistics from a set of race results.

    Returns the daily aggregate structure with combined and per-vantage breakdowns.
    """
    if not races:
        return {
            "date": label,
            "generated_utc": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_races": 0,
            "vantage_points": [],
            "pools": {},
            "gridpool_events": {},
        }

    # Collect vantage points seen
    vantage_points = sorted(set(r.get("vantage", "unknown") for r in races))

    # Collect per-pool data: combined and per-vantage
    pool_data: Dict[str, Dict[str, Any]] = {}
    # Also collect "any template" data (from arrivals_offset_ms instead of nonempty)
    pool_data_any: Dict[str, Dict[str, Any]] = {}

    for race in races:
        vantage = race.get("vantage", "unknown")
        # Use nonempty_arrivals_offset_ms as primary ranking data (full template timing)
        offsets = race.get("nonempty_arrivals_offset_ms") or {}
        # Also use arrivals_offset_ms for "any template" mode
        any_offsets = race.get("arrivals_offset_ms") or {}
        empty_first_pools = set(race.get("empty_first_pools") or [])
        eligible_pools = race.get("eligible_at_start") or list(
            set(list(offsets.keys()) + list(any_offsets.keys()))
        )

        # --- Full Template stats (nonempty) ---
        for pool_name, offset_val in offsets.items():
            try:
                offset = float(offset_val)
            except (TypeError, ValueError):
                continue

            if pool_name not in pool_data:
                pool_data[pool_name] = {
                    "combined": new_accumulator(),
                    "by_vantage": {},
                }

            pd = pool_data[pool_name]

            # Combined stats
            pd["combined"]["offsets"].append(offset)
            pd["combined"]["races_seen"] += 1
            if offset == 0.0:
                pd["combined"]["wins"] += 1
            if pool_name in empty_first_pools:
                pd["combined"]["empty_first_count"] += 1
            # Stale and gap samples for waste calculation
            stale_ms = offset
            gap_ms = 0.0
            empty_to_full = race.get("empty_to_full_ms") or {}
            if pool_name in empty_to_full:
                try:
                    gap_ms = float(empty_to_full[pool_name])
                except (TypeError, ValueError):
                    gap_ms = 0.0
            pd["combined"]["stale_samples"].append(stale_ms)
            pd["combined"]["gap_samples"].append(gap_ms)

            # Per-vantage stats
            if vantage not in pd["by_vantage"]:
                pd["by_vantage"][vantage] = new_accumulator()
            v_acc = pd["by_vantage"][vantage]
            v_acc["offsets"].append(offset)
            v_acc["races_seen"] += 1
            if offset == 0.0:
                v_acc["wins"] += 1
            if pool_name in empty_first_pools:
                v_acc["empty_first_count"] += 1
            v_acc["stale_samples"].append(stale_ms)
            v_acc["gap_samples"].append(gap_ms)

        # --- Any Template stats (arrivals_offset_ms) ---
        for pool_name, offset_val in any_offsets.items():
            try:
                offset = float(offset_val)
            except (TypeError, ValueError):
                continue

            if pool_name not in pool_data_any:
                pool_data_any[pool_name] = {
                    "combined": new_accumulator(),
                    "by_vantage": {},
                }

            pd_any = pool_data_any[pool_name]

            pd_any["combined"]["offsets"].append(offset)
            pd_any["combined"]["races_seen"] += 1
            if offset == 0.0:
                pd_any["combined"]["wins"] += 1
            if pool_name in empty_first_pools:
                pd_any["combined"]["empty_first_count"] += 1
            pd_any["combined"]["stale_samples"].append(offset)
            pd_any["combined"]["gap_samples"].append(0.0)

            if vantage not in pd_any["by_vantage"]:
                pd_any["by_vantage"][vantage] = new_accumulator()
            v_acc_any = pd_any["by_vantage"][vantage]
            v_acc_any["offsets"].append(offset)
            v_acc_any["races_seen"] += 1
            if offset == 0.0:
                v_acc_any["wins"] += 1
            if pool_name in empty_first_pools:
                v_acc_any["empty_first_count"] += 1
            v_acc_any["stale_samples"].append(offset)
            v_acc_any["gap_samples"].append(0.0)

        # Track eligible pools even if they missed the race
        for pool_name in eligible_pools:
            if pool_name not in pool_data:
                pool_data[pool_name] = {
                    "combined": new_accumulator(),
                    "by_vantage": {},
                }
            pool_data[pool_name]["combined"]["races_eligible"] += 1
            if vantage not in pool_data[pool_name]["by_vantage"]:
                pool_data[pool_name]["by_vantage"][vantage] = new_accumulator()
            pool_data[pool_name]["by_vantage"][vantage]["races_eligible"] += 1

            if pool_name not in pool_data_any:
                pool_data_any[pool_name] = {
                    "combined": new_accumulator(),
                    "by_vantage": {},
                }
            pool_data_any[pool_name]["combined"]["races_eligible"] += 1
            if vantage not in pool_data_any[pool_name]["by_vantage"]:
                pool_data_any[pool_name]["by_vantage"][vantage] = new_accumulator()
            pool_data_any[pool_name]["by_vantage"][vantage]["races_eligible"] += 1

    # Build output pools dict with both full and any template stats
    pools_output: Dict[str, Any] = {}
    all_pool_names = set(list(pool_data.keys()) + list(pool_data_any.keys()))

    for pool_name in all_pool_names:
        # Full template stats (nonempty_arrivals_offset_ms)
        if pool_name in pool_data:
            pd = pool_data[pool_name]
            combined_stats = compute_stats(pd["combined"])
            by_vantage_stats = {}
            for vp, acc in pd["by_vantage"].items():
                by_vantage_stats[vp] = compute_stats(acc)
        else:
            combined_stats = compute_stats(new_accumulator())
            by_vantage_stats = {}

        # Any template stats (arrivals_offset_ms)
        if pool_name in pool_data_any:
            pd_any = pool_data_any[pool_name]
            combined_stats_any = compute_stats(pd_any["combined"])
            by_vantage_stats_any = {}
            for vp, acc in pd_any["by_vantage"].items():
                by_vantage_stats_any[vp] = compute_stats(acc)
        else:
            combined_stats_any = compute_stats(new_accumulator())
            by_vantage_stats_any = {}

        pools_output[pool_name] = {
            "combined": combined_stats,
            "by_vantage": by_vantage_stats,
            "any_combined": combined_stats_any,
            "any_by_vantage": by_vantage_stats_any,
        }

    return {
        "date": label,
        "generated_utc": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_races": len(races),
        "vantage_points": vantage_points,
        "pools": pools_output,
        "gridpool_events": _compute_gridpool_event_stats(races),
    }
