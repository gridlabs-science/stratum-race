<script setup lang="ts">
import { computed } from 'vue'
import { useRaceStore } from '@/stores/raceStore'

const store = useRaceStore()

const EVENT_ORDER = [
  'peer_header',
  'local_header',
  'local_node',
  'payout_snapshot',
  'relay_dispatch',
  'synthetic_fast_gridpool',
]

const rows = computed(() => EVENT_ORDER
  .map((name) => {
    const aggregate = store.gridpoolEventData[name]
    return aggregate
      ? { name, aggregate, stats: store.getGridPoolEventStats(name) }
      : null
  })
  .filter((row) => row !== null))

function formatSigned(value: number | null): string {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

function interpretation(value: number | null): string {
  if (value == null) return 'No observation'
  if (value < 0) return 'Before first work'
  if (value > 0) return 'After first work'
  return 'At first work'
}
</script>

<template>
  <section v-if="rows.length > 0" class="event-panel">
    <header class="panel-head">
      <div>
        <h2>Node &amp; GridPool Event Latency</h2>
        <p>Signed milliseconds from the first miner-facing work observed at each vantage.</p>
      </div>
      <span class="origin-note">negative = earlier</span>
    </header>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Event</th>
            <th>Median (ms)</th>
            <th>Average (ms)</th>
            <th>P95 (ms)</th>
            <th>Earlier</th>
            <th>Samples</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.name"
            :class="{ synthetic: row.aggregate.synthetic }"
          >
            <td>
              <strong>{{ row.aggregate.label }}</strong>
              <span v-if="row.aggregate.synthetic" class="model-badge">MODELED</span>
              <small>{{ interpretation(row.stats?.median_ms ?? null) }}</small>
            </td>
            <td>{{ formatSigned(row.stats?.median_ms ?? null) }}</td>
            <td>{{ formatSigned(row.stats?.avg_ms ?? null) }}</td>
            <td>{{ formatSigned(row.stats?.p95_ms ?? null) }}</td>
            <td>{{ row.stats?.before_first_work_pct != null ? `${row.stats.before_first_work_pct.toFixed(1)}%` : '—' }}</td>
            <td>{{ row.stats?.observations ?? 0 }} / {{ row.stats?.races_eligible ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="method-note">
      Synthetic Fast GridPool places the fastest measured local backend at the peer-header arrival time.
      It estimates possible notification headroom; it is not an observed template and never counts as a pool win.
    </p>
  </section>
</template>

<style scoped>
.event-panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
}

.panel-head h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1rem;
}

.panel-head p,
.method-note {
  margin: 0.3rem 0 0;
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.origin-note {
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  white-space: nowrap;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
}

th,
td {
  padding: 0.7rem 1rem;
  border-bottom: 1px solid var(--border);
  text-align: right;
  font-family: var(--font-mono);
  font-size: 0.78rem;
}

th {
  color: var(--text-secondary);
  font-size: 0.68rem;
  text-transform: uppercase;
}

th:first-child,
td:first-child {
  text-align: left;
  font-family: var(--font-sans);
}

td strong {
  display: inline-block;
  color: var(--text-primary);
}

td small {
  display: block;
  margin-top: 0.15rem;
  color: var(--text-secondary);
}

tr.synthetic {
  background: color-mix(in srgb, #e879f9 8%, transparent);
}

.model-badge {
  display: inline-block;
  margin-left: 0.5rem;
  padding: 0.08rem 0.35rem;
  border: 1px dashed #e879f9;
  border-radius: 999px;
  color: #e879f9;
  font-family: var(--font-mono);
  font-size: 0.58rem;
}

.method-note {
  margin: 0;
  padding: 0.75rem 1.25rem;
  line-height: 1.45;
}
</style>
