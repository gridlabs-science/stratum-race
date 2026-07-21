# GridPool StratumRace Deployment

This fork adds native Stratum V2 observation, authenticated multi-vantage
ingestion, and correlation with GridPool's chain-tip telemetry. It remains a
vantage-dependent measurement tool, not proof of global pool performance.

## Main Vantage

The Main configuration compares two cohorts:

- `gridpool-local`: Hydrapool SV1 on `3333`, DATUM SV1 on `23334`, CKPool SV1
  on `3335`, and native GridPool SV2 on `34265`;
- `public-reference`: selected public endpoints also used by upstream
  StratumRace.

Build the native SV2 observer and frontend:

```bash
cargo build --release --manifest-path sv2-observer/Cargo.toml
cd frontend && npm ci && npm run build && cd ..
```

Development launch:

```bash
export STRATUMRACE_SV2_OBSERVER="$PWD/sv2-observer/target/release/sv2-observer"
python3 -m standalone.main \
  --host 127.0.0.1 \
  --port 8080 \
  --data-dir ~/.local/state/gridpool-stratum-race \
  --pools config/gridpool-main.json \
  --pool-group gridpool-study \
  --vantage main-dc \
  --gridpool-url http://127.0.0.1:5000 \
  --ingest-tokens-file ~/.config/gridpool-stratum-race/ingest-tokens.json
```

The ingest token file is untracked and maps each random token to the only
vantage identity it may submit:

```json
{
  "replace-with-at-least-32-random-characters": "evomining-texas",
  "replace-with-another-random-token-value": "detroit"
}
```

Publish `http://127.0.0.1:8080` through the existing Cloudflare Tunnel as
`race.gridpool.net`. The public surface is read-only except for the two ingest
routes, which require a configured token and overwrite any claimed vantage
name with the token-bound identity.

## Remote Agents

Copy `config/gridpool-agent.example.json` to the untracked operator config and
list the local Stratum endpoints available at that site. Keep at least two
public reference endpoints so a race can still be confirmed when only one
local mining server exists.

Create `/etc/gridpool-stratum-race/agent.env`:

```bash
STRATUMRACE_VANTAGE=evomining-texas
STRATUMRACE_API_KEY=<matching token from Main>
```

Use `detroit` for the Detroit vantage. Install the matching systemd unit from
`deploy/systemd/stratum-race-agent.service`. Remote results are compared using
offsets measured on each receiver; cross-host wall-clock timestamps are not
treated as precise latency measurements.

## Interpreting Results

- **Any Template** means the first miner-usable new-parent job. It is the
  protocol-neutral comparison that includes native SV2.
- **Full Template** uses the SV1 Merkle branch to exclude coinbase-only work.
  SV2 Standard Channels intentionally hide transaction count, so SV2 is marked
  `opaque` and omitted from this ranking.
- Local loopback results measure backend construction and emission. Public
  endpoint results include Internet routing from this vantage.
- GridPool correlation records local ZMQ, first peer header, and miner-facing
  work for the same block hash. It does not imply that peer headers currently
  trigger templates, snapshots, or mining.
- Treat fewer than 20 blocks as anecdotal. Prefer 72-hour and 7-day windows.

