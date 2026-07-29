# Preliminary GridPool Multi-Vantage StratumRace Report

Generated: 2026-07-29T12:33:39.482606Z

> Field timing study, not statistical proof. Results describe two controlled
> vantages, their configured endpoints, and this collection window only.

## Executive Summary

The baseline contains **353 matched Bitcoin heights** and
**706 race records** over **62.36 hours**.
Every included height was independently observed from both Main and Oregon.

Across the two vantages, an already-received GridPool peer header preceded the
first sovereign local mining job in **284/706
observations (40.2%)**. Across those early observations, the
combined median lead was **319.6 ms**
with a **940.6 ms P95**. This measures a
hypothetical opportunity for a
header-triggered fast path; GridPool did not mine or activate consensus from
the peer header in this experiment.

Native SV2 was the fastest observed local GridPool lane by median miner-usable
job arrival at both vantages. Its missing-event rate is material because the
SV2 lane was not continuously available over the full window; latency
percentiles describe observed events and must not be read as availability.

## Scope

- Heights: **959751 through 960104**
- UTC window: **2026-07-26T21:55:29.269219Z through 2026-07-29T12:17:21.643330Z**
- Inclusion rule: a height must have one race from every listed vantage
- Timing mode: miner-usable "any template"; SV2 transaction content is opaque
- Reference zero for pool latency: first observed miner-usable job at that same
  vantage, often AtlasPool or Parasite
- Reference zero for GridPool node events: first sovereign local mining job at
  that same vantage; negative values mean the node event came first

## Vantages

| Vantage | Region | Topology | Clock status |
| --- | --- | --- | --- |
| main-dc | Washington, D.C. area | Attached Bitcoin Core; local mining adapters | NTP synchronized at report generation |
| oregon-vps | Oregon VPS | Attached Bitcoin Core; local mining adapters | NTP synchronized at report generation |

Both hosts reported systemd NTP synchronized when this report was generated.
Per-race NTP offset was not retained, so aligned wall-clock comparisons are
appropriate only as operator-controlled observations.

## Miner-Facing Work

| Lane | Vantage | Observed | Missing overall | Missing after first observation | Median | P95 |
| --- | --- | --- | --- | --- | --- | --- |
| GridPool Native SV2 | main-dc | 250/353 | 29.2% | 29.2% | 333.4 ms | 958.8 ms |
| GridPool Native SV2 | oregon-vps | 240/353 | 32.0% | 7.3% | 386.0 ms | 849.5 ms |
| GridPool Hydrapool SV1 | main-dc | 353/353 | 0.0% | 0.0% | 647.5 ms | 1,436.9 ms |
| GridPool Hydrapool SV1 | oregon-vps | 353/353 | 0.0% | 0.0% | 579.2 ms | 1,062.4 ms |
| GridPool CKPool SV1 | main-dc | 341/353 | 3.4% | 3.4% | 743.6 ms | 5,531.9 ms |
| GridPool CKPool SV1 | oregon-vps | 353/353 | 0.0% | 0.0% | 898.8 ms | 2,132.9 ms |
| GridPool DATUM SV1 | main-dc | 353/353 | 0.0% | 0.0% | 952.0 ms | 1,807.0 ms |
| GridPool DATUM SV1 | oregon-vps | 351/353 | 0.6% | 0.6% | 930.0 ms | 1,635.1 ms |
| AtlasPool | main-dc | 353/353 | 0.0% | 0.0% | 0.0 ms | 153.8 ms |
| AtlasPool | oregon-vps | 353/353 | 0.0% | 0.0% | 0.0 ms | 130.9 ms |
| Parasite | main-dc | 351/353 | 0.6% | 0.6% | 72.9 ms | 1,669.0 ms |
| Parasite | oregon-vps | 353/353 | 0.0% | 0.0% | 142.8 ms | 445.4 ms |
| OCEAN | main-dc | 352/353 | 0.3% | 0.3% | 479.5 ms | 2,254.0 ms |
| OCEAN | oregon-vps | 351/353 | 0.6% | 0.6% | 643.8 ms | 1,230.3 ms |
| Public Pool | main-dc | 350/353 | 0.8% | 0.8% | 1,453.0 ms | 5,058.0 ms |
| Public Pool | oregon-vps | 351/353 | 0.6% | 0.6% | 1,417.8 ms | 3,696.4 ms |
| PyBLOCK | main-dc | 353/353 | 0.0% | 0.0% | 676.1 ms | 3,215.9 ms |
| PyBLOCK | oregon-vps | 352/353 | 0.3% | 0.3% | 690.6 ms | 1,942.0 ms |

Missing means no miner-usable event was recorded for that lane in an included
race. It can represent an unavailable lane, reconnect, observer limitation, or
late event outside the race window. It is not automatically a pool failure.
The post-start column removes only the leading pre-deployment interval; it does
not remove later outages or observer gaps.
DATUM's first job was coinbase-only in this sample; the table uses first
miner-usable work consistently and does not claim full-template equivalence.

## GridPool And Node Events

| Event | Vantage | Observed | Missing | Median offset | P95 offset | Early opportunity | Median early lead |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GridPool peer chain-tip | main-dc | 147/353 | 58.4% | -387.5 ms | -62.2 ms | 41.6% | 387.5 ms |
| GridPool peer chain-tip | oregon-vps | 353/353 | 0.0% | 1.3 ms | 509.1 ms | 49.9% | 152.3 ms |
| Local Bitcoin node notification | main-dc | 353/353 | 0.0% | -34.9 ms | -20.0 ms | 99.7% | 34.9 ms |
| Local Bitcoin node notification | oregon-vps | 353/353 | 0.0% | -43.4 ms | -26.9 ms | 99.7% | 43.4 ms |
| Local raw block header | main-dc | 347/353 | 1.7% | -30.5 ms | 27.1 ms | 80.7% | 33.7 ms |
| Local raw block header | oregon-vps | 353/353 | 0.0% | -11.8 ms | 101.4 ms | 79.0% | 17.1 ms |
| GridPool payout snapshot | main-dc | 348/353 | 1.4% | -28.4 ms | -15.6 ms | 98.3% | 28.4 ms |
| GridPool payout snapshot | oregon-vps | 353/353 | 0.0% | -41.2 ms | -25.0 ms | 99.7% | 41.2 ms |
| GridPool relay dispatch | main-dc | 348/353 | 1.4% | 3.0 ms | 35.0 ms | 45.0% | 140.5 ms |
| GridPool relay dispatch | oregon-vps | 353/353 | 0.0% | -6.5 ms | 106.1 ms | 74.8% | 10.9 ms |
| Synthetic Fast GridPool | main-dc | 146/353 | 58.6% | -388.8 ms | -68.1 ms | 41.4% | 387.5 ms |
| Synthetic Fast GridPool | oregon-vps | 138/353 | 60.9% | -258.7 ms | -51.7 ms | 39.1% | 257.3 ms |

`Synthetic Fast GridPool` is a counterfactual: the peer header arrived before
both the attached node notification and first sovereign local work. It assumes
an implementation could immediately create usable work, which the current
runtime intentionally does not do. It therefore estimates an upper-bound
opportunity, not realized mining performance.

## Cross-Vantage Wall-Clock Comparison

The signed column is **Oregon minus Main**. Negative values mean Oregon received
the event first. P95 absolute difference shows geographic spread without
choosing a winner.

| Lane | Paired observations | Median Oregon - Main | P95 absolute spread | Oregon first |
| --- | --- | --- | --- | --- |
| GridPool Native SV2 | 164 | 20.7 ms | 629.1 ms | 47.0% |
| GridPool Hydrapool SV1 | 353 | -107.8 ms | 780.4 ms | 65.7% |
| GridPool CKPool SV1 | 341 | 100.1 ms | 4,906.2 ms | 38.4% |
| GridPool DATUM SV1 | 351 | -65.0 ms | 1,032.2 ms | 53.3% |
| AtlasPool | 353 | -13.9 ms | 359.8 ms | 53.5% |
| Parasite | 351 | 61.2 ms | 1,543.1 ms | 32.8% |
| OCEAN | 350 | 46.9 ms | 1,666.2 ms | 43.1% |
| Public Pool | 350 | 3.6 ms | 2,612.8 ms | 48.0% |
| PyBLOCK | 352 | 19.0 ms | 1,554.0 ms | 12.8% |

## Interpretation

1. Multi-vantage collection is operational: the same 350 block transitions
   were captured at two independently hosted, attached-node vantages.
2. Local template construction adds measurable latency after each attached node
   learns the tip. Native SV2 currently has the lowest median among the four
   GridPool-local lanes, while tail latency and availability still need work.
3. Peer chain-tip relay often arrives too late to improve local work, but it
   arrived early in about 40.2% of observations. The measured
   lead in those cases is large enough to justify continued telemetry and
   careful fast-path research.
4. These results do not justify making peer headers a consensus clock or mining
   unvalidated blocks. V2.2 consensus remains independent of notification
   transport.

## Data Quality And Caveats

- The window is roughly 62 hours, not a completed
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
