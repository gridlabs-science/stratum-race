<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRaceStore } from '@/stores/raceStore'
import { useTimezone } from '@/composables/useTimezone'
import { useVantageNames } from '@/composables/useVantageNames'
import type { RaceResult, RecentBlock } from '@/types'
import { buildUnifiedTimeline } from '@/utils/blockTimeline'
import type { UnifiedTimelineMarker, UnifiedVantageTimeline } from '@/utils/blockTimeline'

const route = useRoute()
const router = useRouter()
const store = useRaceStore()
const { formatTimestamp } = useTimezone()
const { formatVantage } = useVantageNames()

/** Block height from route params */
const blockHeight = computed(() => Number(route.params.height))

/**
 * Find all matching races for this block height across vantage points.
 * Multiple vantage points may have observed the same block.
 */
const recentMatches = computed<RecentBlock[]>(() => {
  return store.recentBlocks.filter(
    (b) => b.height === blockHeight.value,
  )
})

/** Full race results fetched from the backend (contains per-pool offsets) */
const fullRaces = ref<RaceResult[]>([])
const isLoading = ref(false)
const loadError = ref(false)

/**
 * Fetch full race JSON files for the given block.
 * Uses the RecentBlock summary to construct the API path.
 */
async function fetchFullRaces() {
  if (recentMatches.value.length === 0) return
  isLoading.value = true
  loadError.value = false
  fullRaces.value = []

  const results: RaceResult[] = []

  for (const block of recentMatches.value) {
    // Build the /api/races/... path for the race file
    const dt = new Date(block.epoch * 1000)
    const year = dt.getUTCFullYear()
    const month = String(dt.getUTCMonth() + 1).padStart(2, '0')
    const day = String(dt.getUTCDate()).padStart(2, '0')
    // Null-height races are stored as unknown-<epoch>-<vantage>.json
    // (epoch disambiguates multiple unknown blocks on the same day)
    const heightPart = block.height != null ? String(block.height) : `unknown-${Math.floor(block.epoch)}`
    const vantage = block.vantage
    const url = `/api/races/${year}/${month}/${day}/${heightPart}-${vantage}.json`

    try {
      const response = await fetch(url)
      if (response.ok) {
        const data: RaceResult = await response.json()
        results.push(data)
      }
    } catch {
      // Silently skip — will show summary fallback
    }
  }

  fullRaces.value = results
  if (results.length === 0) {
    loadError.value = true
  }
  isLoading.value = false
}

// Fetch full race data when the component mounts or block height changes
onMounted(fetchFullRaces)
watch(blockHeight, fetchFullRaces)
// Also retry when recentMatches becomes populated (handles deep-link race condition)
watch(recentMatches, (newVal) => {
  if (newVal.length > 0 && fullRaces.value.length === 0 && !isLoading.value) {
    fetchFullRaces()
  }
})

/**
 * Use full race data when available, otherwise fall back to recent block summaries.
 * The races computed uses full data for timeline rendering.
 */
const races = computed(() => fullRaces.value.length > 0 ? fullRaces.value : recentMatches.value)

/** Primary race data (first match or null) */
const primaryRace = computed(() => races.value[0] ?? null)

const unifiedTimelines = computed(() => fullRaces.value.map(buildUnifiedTimeline))

const endpointCount = computed(() => {
  const race = primaryRace.value as RaceResult | null
  if (!race) return 0
  return new Set([
    ...Object.keys(race.pool_cohorts ?? {}),
    ...Object.keys(race.arrivals_offset_ms ?? {}),
  ]).size
})

/** Block metadata */
const blockMiner = computed(() => {
  const race = primaryRace.value
  if (!race) return 'Unknown'
  return (race as any).block_miner || (race as any).miner || 'Unknown'
})

/** Winners per vantage point */
const winnersPerVantage = computed(() => {
  return races.value.map((race: any) => ({
    vantage: race.vantage,
    winner: race.winner_nonempty || race.winner || '—',
  }))
})
const totalSpread = computed(() => {
  const race = primaryRace.value
  if (!race) return '—'
  // Full race has arrivals_offset_ms; summary has spread_ms
  if ((race as any).arrivals_offset_ms) {
    const offsets = Object.values((race as any).arrivals_offset_ms) as number[]
    if (offsets.length > 0) {
      return (Math.max(...offsets) - Math.min(...offsets)).toFixed(1)
    }
  }
  return (race as any).spread_ms?.toFixed(1) ?? '—'
})

/** Shortened prevhash is not in RecentBlock type, but we show block height context */
const formattedTime = computed(() => {
  if (!primaryRace.value) return '—'
  const race = primaryRace.value as any
  // Full race uses first_epoch; summary uses epoch
  const epoch = race.first_epoch ?? race.epoch
  return epoch ? formatTimestamp(epoch) : '—'
})

function formatLatency(value: number): string {
  if (value < 1000) return `${value.toFixed(1)} ms`
  return `${(value / 1000).toFixed(3)} s`
}

function goBack() {
  router.push({ name: 'recent-blocks' })
}

/**
 * Compute the left position percentage for a marker on the timeline bar.
 */
function markerPosition(marker: UnifiedTimelineMarker, timeline: UnifiedVantageTimeline): string {
  return `${Math.min(100, Math.max(0, marker.offsetMs / timeline.durationMs * 100))}%`
}

function axisTicks(timeline: UnifiedVantageTimeline) {
  return [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    ratio,
    label: formatLatency(timeline.durationMs * ratio),
  }))
}

function rowLabel(rowId: string, label: string): string {
  return rowId.startsWith('endpoint-') ? store.displayName(label) : label
}

function markerTitle(marker: UnifiedTimelineMarker): string {
  const details = [
    marker.label,
    formatLatency(marker.offsetMs),
    new Date(marker.epochMs).toISOString(),
    marker.transport,
    marker.source,
  ].filter(Boolean)
  return details.join(' · ')
}
</script>

<template>
  <div class="block-detail-view">
    <!-- Back button -->
    <button class="back-btn" @click="goBack" aria-label="Back to Recent Blocks">
      ← Back to Recent Blocks
    </button>

    <!-- Not found state -->
    <div v-if="isLoading" class="not-found">
      <p>Loading race data...</p>
    </div>
    <div v-else-if="!primaryRace && recentMatches.length === 0" class="not-found">
      <h2>Block Not in Recent Data</h2>
      <p>Block {{ blockHeight.toLocaleString() }} is not available in the recent blocks list.</p>
      <button @click="goBack">Return to Leaderboard</button>
    </div>

    <!-- Block detail content -->
    <template v-else-if="primaryRace">
      <!-- Block metadata header -->
      <header class="block-header">
        <h2 class="block-title">Block {{ blockHeight.toLocaleString() }}</h2>
        <div class="metadata-grid">
          <div class="meta-item">
            <span class="meta-label">Time</span>
            <span class="meta-value">{{ formattedTime }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Block Miner</span>
            <span class="meta-value">{{ blockMiner }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Winner (Full Template)</span>
            <div class="meta-winners">
              <div v-for="w in winnersPerVantage" :key="w.vantage" class="winner-entry">
                <span class="winner-vantage">{{ formatVantage(w.vantage) }}:</span>
                <span class="meta-value winner-value">{{ store.displayName(w.winner) }}</span>
              </div>
            </div>
          </div>
          <div class="meta-item">
            <span class="meta-label">Total Spread</span>
            <span class="meta-value">{{ totalSpread }} ms</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Pools</span>
            <span class="meta-value">{{ endpointCount }}</span>
          </div>
        </div>
      </header>

      <div class="marker-legend" aria-label="Timeline legend">
        <span class="legend-item legend-public">Public endpoint</span>
        <span class="legend-item legend-local">Local endpoint</span>
        <span class="legend-item legend-protocol">Node / GridPool event</span>
        <span class="legend-item">
          <span class="legend-marker marker-full"></span>Final full work
        </span>
        <span class="legend-item">
          <span class="legend-marker marker-empty"></span>Initial empty work
        </span>
        <span class="legend-item">
          <span class="legend-marker marker-opaque"></span>SV2 usable job
        </span>
      </div>

      <section
        v-for="timeline in unifiedTimelines"
        :key="timeline.vantage"
        class="timeline-section"
        :aria-label="`${formatVantage(timeline.vantage)} complete event timeline`"
      >
        <header class="timeline-heading">
          <div>
            <span class="timeline-kicker">Complete event path</span>
            <h3>{{ formatVantage(timeline.vantage) }}</h3>
          </div>
          <div class="timeline-range">
            <strong>{{ formatLatency(timeline.durationMs) }}</strong>
            <span>{{ new Date(timeline.startEpochMs).toISOString() }}</span>
          </div>
        </header>

        <div class="timeline-axis">
          <span class="axis-origin">Earliest event</span>
          <span
            v-for="tick in axisTicks(timeline)"
            :key="tick.ratio"
            class="axis-tick"
            :style="{ left: `${tick.ratio * 100}%` }"
          >{{ tick.label }}</span>
        </div>

        <div v-for="group in timeline.groups" :key="group.category" class="timeline-group" :class="`group-${group.category}`">
          <div class="group-heading">{{ group.label }}</div>
          <div v-for="row in group.rows" :key="row.id" class="timeline-row" :class="[`row-${row.category}`, { 'row-missing': row.status === 'missing' }]">
            <div class="row-identity">
              <span class="row-name">{{ rowLabel(row.id, row.label) }}</span>
              <span v-if="row.status === 'missing'" class="row-status">Not observed</span>
              <span v-else class="row-status">{{ formatLatency(row.markers[row.markers.length - 1].offsetMs) }}</span>
            </div>
            <div class="row-track">
              <span class="track-line"></span>
              <button
                v-for="marker in row.markers"
                :key="`${marker.kind}-${marker.epochMs}`"
                type="button"
                class="timeline-marker"
                :class="`marker-${marker.kind}`"
                :style="{ left: markerPosition(marker, timeline) }"
                :title="markerTitle(marker)"
                :aria-label="markerTitle(marker)"
              >
                <span class="marker-time">{{ formatLatency(marker.offsetMs) }}</span>
              </button>
            </div>
          </div>
        </div>

        <p class="timeline-note">
          GridPool peer-header timing is measured notification lead only. Peer headers do not currently activate mining templates.
        </p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.block-detail-view {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem;
}

.back-btn {
  margin-bottom: 1.5rem;
  background: var(--surface-elevated);
  color: var(--accent);
  font-weight: 500;
  font-size: 0.875rem;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
}

.back-btn:hover {
  background: var(--border);
}

/* Not found state */
.not-found {
  text-align: center;
  padding: 3rem 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
}

.not-found h2 {
  margin-bottom: 0.75rem;
  color: var(--text-primary);
}

.not-found p {
  color: var(--text-secondary);
  margin-bottom: 1.5rem;
}

/* Block header */
.block-header {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.block-title {
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 1rem;
  color: var(--text-primary);
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.meta-label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.meta-value {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--text-primary);
}

.winner-value {
  color: var(--accent);
  font-weight: 600;
}

.meta-winners {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.winner-entry {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.winner-vantage {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.marker-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  padding: 0.65rem 1rem;
  margin-bottom: 0.75rem;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.legend-public,
.legend-local,
.legend-protocol {
  padding-left: 0.55rem;
  border-left: 3px solid;
}

.legend-public { border-color: #f59e0b; }
.legend-local { border-color: #22c55e; }
.legend-protocol { border-color: #38bdf8; }

.legend-marker {
  width: 9px;
  height: 9px;
  border: 2px solid var(--accent);
  border-radius: 50%;
}

.legend-marker.marker-full {
  background: var(--accent);
}

.legend-marker.marker-empty {
  border-color: var(--warning);
  background: transparent;
}

.legend-marker.marker-opaque {
  border-radius: 1px;
  transform: rotate(45deg);
  background: var(--accent);
}

.timeline-section {
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  padding: 1.25rem;
}

.timeline-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  min-width: 760px;
  margin-bottom: 1.25rem;
}

.timeline-heading h3 {
  margin: 0.2rem 0 0;
  color: var(--text-primary);
  font-size: 1.05rem;
}

.timeline-kicker {
  color: var(--accent);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.timeline-range {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.2rem;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 0.65rem;
}

.timeline-range strong {
  color: var(--text-primary);
  font-size: 0.9rem;
}

.timeline-axis {
  position: relative;
  min-width: 760px;
  height: 38px;
  margin-left: 230px;
  border-top: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 0.625rem;
  font-family: var(--font-mono);
}

.axis-origin {
  position: absolute;
  right: calc(100% + 16px);
  top: -0.45rem;
  width: 210px;
  color: var(--text-secondary);
  text-align: right;
}

.axis-tick {
  position: absolute;
  top: 0;
  height: 13px;
  padding-top: 16px;
  transform: translateX(-50%);
  border-left: 1px solid var(--border);
  white-space: nowrap;
}

.axis-tick:last-child {
  transform: translateX(-100%);
}

.timeline-group {
  min-width: 990px;
  margin-bottom: 0.8rem;
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: 0.35rem;
  background: color-mix(in srgb, var(--surface-elevated) 45%, transparent);
}

.group-public { border-left-color: #f59e0b; }
.group-protocol { border-left-color: #38bdf8; }
.group-local { border-left-color: #22c55e; }
.group-other { border-left-color: var(--text-secondary); }

.group-heading {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.timeline-row {
  display: flex;
  align-items: center;
  min-height: 48px;
  padding: 0 0.75rem;
  border-bottom: 1px solid var(--border);
}

.timeline-row:last-child {
  border-bottom: none;
}

.row-identity {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 215px;
  flex-shrink: 0;
  gap: 0.15rem;
  padding-right: 1rem;
}

.row-name {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-status {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 0.65rem;
}

.row-track {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 34px;
}

.track-line {
  position: absolute;
  top: 50%;
  right: 0;
  left: 0;
  height: 1px;
  background: var(--border);
}

.timeline-marker {
  appearance: none;
  position: absolute;
  top: 50%;
  z-index: 2;
  transform: translate(-50%, -50%);
  width: 13px;
  height: 13px;
  padding: 0;
  border: 2px solid currentColor;
  border-radius: 50%;
  background: currentColor;
  color: var(--accent);
  cursor: help;
}

.row-public .timeline-marker { color: #f59e0b; }
.row-local .timeline-marker { color: #22c55e; }
.row-protocol .timeline-marker { color: #38bdf8; }
.row-other .timeline-marker { color: var(--text-secondary); }

.timeline-marker.marker-empty {
  background: var(--surface);
}

.timeline-marker.marker-opaque {
  border-radius: 2px;
  transform: translate(-50%, -50%) rotate(45deg);
}

.timeline-marker.marker-node,
.timeline-marker.marker-snapshot,
.timeline-marker.marker-relay {
  border-radius: 3px;
}

.timeline-marker.marker-peer {
  width: 15px;
  height: 15px;
  box-shadow: 0 0 0 4px rgb(56 189 248 / 18%);
}

.marker-time {
  position: absolute;
  top: -22px;
  left: 50%;
  transform: translateX(-50%);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 0.6rem;
  white-space: nowrap;
  pointer-events: none;
}

.timeline-marker.marker-opaque .marker-time {
  transform: translateX(-50%) rotate(-45deg);
}

.row-missing .track-line {
  opacity: 0.35;
  background: repeating-linear-gradient(90deg, var(--border) 0 5px, transparent 5px 10px);
}

.timeline-note {
  min-width: 760px;
  margin: 1rem 0 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
  line-height: 1.45;
}

@media (max-width: 768px) {
  .block-detail-view {
    padding: 1rem;
  }

  .metadata-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 480px) {
  .metadata-grid {
    grid-template-columns: 1fr;
  }
}
</style>
