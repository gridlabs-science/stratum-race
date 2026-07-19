<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRaceStore } from '@/stores/raceStore'
import { useVantageNames } from '@/composables/useVantageNames'
import type { TimeFrame, PoolStats, RecentBlock, RaceResult } from '@/types'

const route = useRoute()
const router = useRouter()
const store = useRaceStore()
const { formatVantage } = useVantageNames()

const VANTAGE_COLORS = ['var(--accent)', '#f59e0b', '#10b981', '#ec4899', '#8b5cf6']

/** Pool name from route params */
const poolName = computed(() => decodeURIComponent(route.params.poolName as string))

/** Pool config entry */
const poolConfigEntry = computed(() =>
  store.poolConfig.find((p) => p.name === poolName.value)
)

/** Whether this pool exists in config */
const poolExists = computed(() => !!poolConfigEntry.value)

/** Local time frame (independent of global leaderboard) */
const localTimeFrame = ref<TimeFrame>('last50')
const isLoadingStats = ref(false)
const localLeaderboard = ref<Record<string, any>>({})

/** Race files fetched for scatter plot */
const raceFiles = ref<RaceResult[]>([])
const isLoadingRaces = ref(false)

/** Map time frame to aggregate file path */
const TIME_FRAME_PATHS: Record<TimeFrame, string> = {
  last10: 'recent-10',
  last50: 'recent-50',
  '24h': 'last-24h',
  '7d': 'last-7d',
}

/** Fetch aggregate for stats cards */
async function loadStats() {
  isLoadingStats.value = true
  try {
    const response = await fetch(`/api/aggregates/${TIME_FRAME_PATHS[localTimeFrame.value]}.json`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    localLeaderboard.value = data.pools ?? {}
  } catch (error) {
    console.error('Failed to load pool stats:', error)
    localLeaderboard.value = {}
  } finally {
    isLoadingStats.value = false
  }
}

/** Fetch individual race files for scatter plot */
async function loadRaceFiles() {
  isLoadingRaces.value = true

  // Fetch full recent-blocks.json directly (store caps at 40, we need up to 110)
  let blocks: RecentBlock[] = []
  try {
    const resp = await fetch('/api/recent/recent-blocks.json')
    if (resp.ok) {
      blocks = await resp.json()
    }
  } catch { /* fall back to store */ }
  if (blocks.length === 0) {
    blocks = store.recentBlocks
  }
  if (blocks.length === 0) {
    isLoadingRaces.value = false
    return
  }

  // Deduplicate by height+vantage, take top N unique BLOCKS (not entries)
  const limit = localTimeFrame.value === 'last10' ? 10 : 50
  const seenHeights = new Set<number>()
  const blocksToFetch: RecentBlock[] = []

  for (const block of blocks) {
    if (block.height == null) continue
    // Track unique block heights (each vantage reporting same height counts as one block)
    seenHeights.add(block.height)
    if (seenHeights.size > limit) break
    blocksToFetch.push(block)
  }

  // Fetch race files concurrently (batch of 10 at a time)
  const results: RaceResult[] = []
  const batchSize = 10

  for (let i = 0; i < blocksToFetch.length; i += batchSize) {
    const batch = blocksToFetch.slice(i, i + batchSize)
    const promises = batch.map(async (block) => {
      const dt = new Date(block.epoch * 1000)
      const year = dt.getUTCFullYear()
      const month = String(dt.getUTCMonth() + 1).padStart(2, '0')
      const day = String(dt.getUTCDate()).padStart(2, '0')
      const heightPart = block.height != null ? String(block.height) : `unknown-${Math.floor(block.epoch)}`
      const url = `/api/races/${year}/${month}/${day}/${heightPart}-${block.vantage}.json`
      try {
        const resp = await fetch(url)
        if (resp.ok) return await resp.json() as RaceResult
      } catch { /* skip */ }
      return null
    })
    const batchResults = await Promise.all(promises)
    for (const r of batchResults) {
      if (r) results.push(r)
    }
  }

  raceFiles.value = results
  isLoadingRaces.value = false
}

/** Pool stats from the local aggregate */
const poolAggregate = computed(() => localLeaderboard.value[poolName.value])

const combinedStats = computed<PoolStats | null>(() => poolAggregate.value?.combined ?? null)

const vantageStats = computed<Record<string, PoolStats>>(() =>
  poolAggregate.value?.by_vantage ?? {}
)

/** All known vantage points (sorted for deterministic colors) */
const allVantages = computed(() => {
  const set = new Set<string>()
  for (const agg of Object.values(localLeaderboard.value) as any[]) {
    if (agg?.by_vantage) {
      for (const v of Object.keys(agg.by_vantage)) set.add(v)
    }
  }
  return [...set].sort()
})

function getVantageColor(vantage: string): string {
  const idx = allVantages.value.indexOf(vantage)
  return VANTAGE_COLORS[idx >= 0 ? idx % VANTAGE_COLORS.length : 0]
}

/** Scatter plot data points */
interface ScatterPoint {
  height: number
  offset: number
  vantage: string
  isWin: boolean
}

const scatterPoints = computed<ScatterPoint[]>(() => {
  if (raceFiles.value.length === 0) return []

  const points: ScatterPoint[] = []
  for (const race of raceFiles.value) {
    const offsets = race.nonempty_arrivals_offset_ms ?? {}
    const offset = offsets[poolName.value]
    if (offset != null && race.block_height != null) {
      points.push({
        height: race.block_height,
        offset,
        vantage: race.vantage,
        isWin: offset === 0,
      })
    }
  }

  // Sort by height ascending for the x-axis
  points.sort((a, b) => a.height - b.height)
  return points
})

/** Unique block heights for alternating bands */
const uniqueHeights = computed(() => {
  const heights = [...new Set(scatterPoints.value.map(p => p.height))].sort((a, b) => a - b)
  return heights
})

/** Tooltip data: all points grouped by block height */
interface TooltipBlock {
  height: number
  miner: string
  entries: { vantage: string; offset: number; isWin: boolean; isOverallWinner: boolean }[]
}

const tooltipByHeight = computed<Map<number, TooltipBlock>>(() => {
  const map = new Map<number, TooltipBlock>()
  for (const race of raceFiles.value) {
    if (race.block_height == null) continue
    const height = race.block_height
    if (!map.has(height)) {
      map.set(height, { height, miner: (race as any).block_miner || 'Unknown', entries: [] })
    }
    const offsets = race.nonempty_arrivals_offset_ms ?? {}
    const poolOffset = offsets[poolName.value]
    if (poolOffset != null) {
      map.get(height)!.entries.push({
        vantage: race.vantage,
        offset: poolOffset,
        isWin: poolOffset === 0,
        isOverallWinner: race.winner_nonempty === poolName.value,
      })
    }
  }
  return map
})

/** Custom tooltip state (instant on hover) */
const tooltipVisible = ref(false)
const tooltipX = ref(0)
const tooltipY = ref(0)
const tooltipContent = ref<TooltipBlock | null>(null)

function showTooltip(event: MouseEvent, point: ScatterPoint) {
  const block = tooltipByHeight.value.get(point.height)
  if (block) {
    tooltipContent.value = block
  } else {
    tooltipContent.value = { height: point.height, miner: 'Unknown', entries: [{ vantage: point.vantage, offset: point.offset, isWin: point.isWin, isOverallWinner: point.isWin }] }
  }
  tooltipX.value = event.clientX
  tooltipY.value = event.clientY
  tooltipVisible.value = true
}

function showTooltipForHeight(event: MouseEvent, height: number) {
  const block = tooltipByHeight.value.get(height)
  if (block) {
    tooltipContent.value = block
    tooltipX.value = event.clientX
    tooltipY.value = event.clientY
    tooltipVisible.value = true
  }
}

function hideTooltip() {
  tooltipVisible.value = false
}

/** SVG chart dimensions and computed scales */
const chartPadding = { top: 20, right: 20, bottom: 50, left: 85 }
const chartWidth = 830
const chartHeight = 310

const xMin = computed(() => scatterPoints.value.length > 0 ? Math.min(...scatterPoints.value.map(p => p.height)) : 0)
const xMax = computed(() => scatterPoints.value.length > 0 ? Math.max(...scatterPoints.value.map(p => p.height)) : 1)
const yMax = computed(() => {
  if (scatterPoints.value.length === 0) return 100
  const max = Math.max(...scatterPoints.value.map(p => p.offset))
  return max > 0 ? max * 1.1 : 100 // 10% headroom
})

function scaleX(height: number): number {
  const range = xMax.value - xMin.value || 1
  return chartPadding.left + ((height - xMin.value) / range) * (chartWidth - chartPadding.left - chartPadding.right)
}

function scaleY(offset: number): number {
  return chartPadding.top + (1 - offset / yMax.value) * (chartHeight - chartPadding.top - chartPadding.bottom)
}

/** Y-axis tick marks */
const yTicks = computed(() => {
  const max = yMax.value
  const count = 5
  const step = max / count
  return Array.from({ length: count + 1 }, (_, i) => Math.round(i * step))
})

/** X-axis tick marks (show ~5 labels) */
const xTicks = computed(() => {
  const pts = scatterPoints.value
  if (pts.length === 0) return []
  const min = xMin.value
  const max = xMax.value
  const range = max - min || 1
  const count = Math.min(5, pts.length)
  const step = range / count
  return Array.from({ length: count + 1 }, (_, i) => Math.round(min + i * step))
})

/** Compute the band width per block height for alternating backgrounds */
function bandX(heightIdx: number): number {
  if (uniqueHeights.value.length <= 1) return chartPadding.left
  const height = uniqueHeights.value[heightIdx]
  const prevHeight = heightIdx > 0 ? uniqueHeights.value[heightIdx - 1] : null
  
  const x = scaleX(height)
  const halfLeft = prevHeight != null ? (x - scaleX(prevHeight)) / 2 : (chartWidth - chartPadding.left - chartPadding.right) / uniqueHeights.value.length / 2
  return x - halfLeft
}

function bandWidth(heightIdx: number): number {
  if (uniqueHeights.value.length <= 1) return chartWidth - chartPadding.left - chartPadding.right
  const height = uniqueHeights.value[heightIdx]
  const prevHeight = heightIdx > 0 ? uniqueHeights.value[heightIdx - 1] : null
  const nextHeight = heightIdx < uniqueHeights.value.length - 1 ? uniqueHeights.value[heightIdx + 1] : null
  
  const x = scaleX(height)
  const halfLeft = prevHeight != null ? (x - scaleX(prevHeight)) / 2 : (nextHeight != null ? (scaleX(nextHeight) - x) / 2 : 20)
  const halfRight = nextHeight != null ? (scaleX(nextHeight) - x) / 2 : halfLeft
  return halfLeft + halfRight
}

/** Time frame selection handler */
async function selectFrame(frame: TimeFrame) {
  localTimeFrame.value = frame
  await Promise.all([loadStats(), loadRaceFiles()])
}

function goBack() {
  router.push({ name: 'leaderboard' })
}

// Initial load
onMounted(async () => {
  if (store.poolConfig.length === 0) {
    await store.loadPoolConfig()
  }
  if (store.recentBlocks.length === 0) {
    await store.loadRecentBlocks()
  }
  await Promise.all([loadStats(), loadRaceFiles()])
})

// Reload when pool name changes (in-page navigation)
watch(poolName, async () => {
  await Promise.all([loadStats(), loadRaceFiles()])
})
</script>

<template>
  <div class="pool-detail-view">
    <!-- Back button -->
    <button class="back-btn" @click="goBack" aria-label="Back to Leaderboard">
      ← Back to Leaderboard
    </button>

    <!-- Pool not found -->
    <div v-if="!poolExists && !isLoadingStats" class="not-found">
      <h2>Pool Not Found</h2>
      <p>"{{ poolName }}" is not a recognized pool in the current configuration.</p>
      <button @click="goBack">Return to Leaderboard</button>
    </div>

    <!-- Pool detail content -->
    <template v-else-if="poolExists">
      <!-- Pool header + stats cards -->
      <header class="pool-header">
        <div class="pool-identity">
          <h2 class="pool-title">{{ poolConfigEntry!.display_name }}</h2>
          <div class="pool-meta-tags">
            <span class="tag tag-type">{{ (poolConfigEntry as any).pool_type === 'solo' ? 'Solo' : 'Shared' }}</span>
            <span class="tag tag-operator">{{ poolConfigEntry!.operator }}</span>
          </div>
        </div>
      </header>

      <!-- Stats cards -->
      <div v-if="isLoadingStats && !combinedStats" class="loading-state">Loading stats...</div>
      <div v-else-if="!combinedStats" class="no-data-state">
        <p>No data available for this pool in the selected time frame.</p>
      </div>
      <div v-else class="stats-grid">
        <!-- Combined stats card -->
        <div class="stat-card stat-card-combined">
          <h3 class="card-label">Combined</h3>
          <div class="stat-row">
            <span class="stat-name">Median Offset</span>
            <span class="stat-value">{{ combinedStats.median_ms != null ? combinedStats.median_ms.toFixed(1) + ' ms' : '—' }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-name">Wins</span>
            <span class="stat-value">{{ combinedStats.wins }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-name">Win %</span>
            <span class="stat-value">{{ combinedStats.win_pct.toFixed(1) }}%</span>
          </div>
          <div class="stat-row">
            <span class="stat-name">Races Seen</span>
            <span class="stat-value">{{ combinedStats.races_seen }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-name">P95</span>
            <span class="stat-value">{{ combinedStats.p95_ms != null ? combinedStats.p95_ms.toFixed(1) + ' ms' : '—' }}</span>
          </div>
        </div>

        <!-- Per-vantage stat cards -->
        <div
          v-for="vantage in allVantages"
          :key="vantage"
          class="stat-card"
          :style="{ borderTopColor: getVantageColor(vantage) }"
        >
          <h3 class="card-label">
            <span class="vantage-dot" :style="{ backgroundColor: getVantageColor(vantage) }"></span>
            {{ formatVantage(vantage) }}
          </h3>
          <template v-if="vantageStats[vantage]">
            <div class="stat-row">
              <span class="stat-name">Median Offset</span>
              <span class="stat-value">{{ vantageStats[vantage].median_ms != null ? vantageStats[vantage].median_ms!.toFixed(1) + ' ms' : '—' }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-name">Wins</span>
              <span class="stat-value">{{ vantageStats[vantage].wins }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-name">Win %</span>
              <span class="stat-value">{{ vantageStats[vantage].win_pct.toFixed(1) }}%</span>
            </div>
            <div class="stat-row">
              <span class="stat-name">Races Seen</span>
              <span class="stat-value">{{ vantageStats[vantage].races_seen }}</span>
            </div>
          </template>
          <template v-else>
            <p class="no-vantage-data">No data</p>
          </template>
        </div>
      </div>

      <!-- Scatter plot section -->
      <section class="scatter-section">
        <div class="scatter-header">
          <h3 class="section-title">Offset Timeline</h3>
          <div class="timeframe-filter">
            <span class="filter-label">Period:</span>
            <div class="frame-buttons">
              <button
                :class="{ active: localTimeFrame === 'last10' }"
                @click="selectFrame('last10')"
                :disabled="isLoadingStats"
              >Last 10</button>
              <button
                :class="{ active: localTimeFrame === 'last50' }"
                @click="selectFrame('last50')"
                :disabled="isLoadingStats"
              >Last 50</button>
            </div>
          </div>
        </div>

        <div v-if="isLoadingRaces && scatterPoints.length === 0" class="loading-state">Loading race data...</div>
        <div v-else-if="scatterPoints.length === 0" class="no-data-state">
          <p>No race data found for this pool in the selected window.</p>
        </div>
        <div v-else class="scatter-chart-container">
          <!-- Vantage legend -->
          <div class="vantage-legend">
            <span
              v-for="vp in allVantages"
              :key="vp"
              class="legend-item"
            >
              <span class="legend-dot" :style="{ backgroundColor: getVantageColor(vp) }"></span>
              {{ formatVantage(vp) }}
            </span>
            <span class="legend-item">
              <span class="legend-marker-filled"></span>
              Win
            </span>
            <span class="legend-item">
              <span class="legend-marker-hollow"></span>
              Non-win
            </span>
          </div>

          <svg
            class="scatter-svg"
            :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
            preserveAspectRatio="xMidYMid meet"
            aria-label="Pool offset scatter plot"
          >
            <!-- Alternating vertical bands per block -->
            <rect
              v-for="(height, idx) in uniqueHeights"
              :key="'band-' + height"
              :x="bandX(idx)"
              :y="chartPadding.top"
              :width="bandWidth(idx)"
              :height="chartHeight - chartPadding.top - chartPadding.bottom"
              :fill="idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.05)'"
            />

            <!-- Y-axis grid lines -->
            <line
              v-for="tick in yTicks"
              :key="'yg-' + tick"
              :x1="chartPadding.left"
              :y1="scaleY(tick)"
              :x2="chartWidth - chartPadding.right"
              :y2="scaleY(tick)"
              class="grid-line"
            />
            <!-- Y-axis labels -->
            <text
              v-for="tick in yTicks"
              :key="'yl-' + tick"
              :x="chartPadding.left - 8"
              :y="scaleY(tick) + 4"
              class="axis-label"
              text-anchor="end"
            >{{ tick }}</text>
            <!-- Y-axis title -->
            <text
              :x="14"
              :y="chartHeight / 2"
              class="axis-title"
              text-anchor="middle"
              transform="rotate(-90, 14, 150)"
            >Offset (ms)</text>

            <!-- X-axis labels -->
            <text
              v-for="tick in xTicks"
              :key="'xl-' + tick"
              :x="scaleX(tick)"
              :y="chartHeight - chartPadding.bottom + 18"
              class="axis-label"
              text-anchor="middle"
            >{{ tick }}</text>
            <!-- X-axis title -->
            <text
              :x="(chartWidth - chartPadding.left - chartPadding.right) / 2 + chartPadding.left"
              :y="chartHeight - chartPadding.bottom + 38"
              class="axis-title"
              text-anchor="middle"
            >Block Height</text>

            <!-- Zero line (wins) -->
            <line
              :x1="chartPadding.left"
              :y1="scaleY(0)"
              :x2="chartWidth - chartPadding.right"
              :y2="scaleY(0)"
              class="zero-line"
            />

            <!-- Data points: filled = win, hollow ring = non-win -->
            <template v-for="(point, idx) in scatterPoints" :key="idx">
              <!-- Win: filled circle -->
              <circle
                v-if="point.isWin"
                :cx="scaleX(point.height)"
                :cy="scaleY(point.offset)"
                r="6"
                :fill="getVantageColor(point.vantage)"
                stroke="none"
                class="data-point"
                @mouseenter="showTooltip($event, point)"
                @mouseleave="hideTooltip"
              />
              <!-- Non-win: hollow ring -->
              <circle
                v-else
                :cx="scaleX(point.height)"
                :cy="scaleY(point.offset)"
                r="5"
                fill="transparent"
                :stroke="getVantageColor(point.vantage)"
                stroke-width="2"
                class="data-point"
                @mouseenter="showTooltip($event, point)"
                @mouseleave="hideTooltip"
              />
            </template>

            <!-- Invisible hover rects over each band (tooltip anywhere in the column) -->
            <rect
              v-for="(height, idx) in uniqueHeights"
              :key="'hover-' + height"
              :x="bandX(idx)"
              :y="chartPadding.top"
              :width="bandWidth(idx)"
              :height="chartHeight - chartPadding.top - chartPadding.bottom"
              fill="transparent"
              class="band-hover"
              @mouseenter="showTooltipForHeight($event, height)"
              @mousemove="showTooltipForHeight($event, height)"
              @mouseleave="hideTooltip"
            />
          </svg>

          <!-- Custom instant tooltip -->
          <div
            v-if="tooltipVisible && tooltipContent"
            class="custom-tooltip"
            :style="{ left: tooltipX + 12 + 'px', top: tooltipY - 10 + 'px' }"
          >
            <div class="tooltip-header">Block {{ tooltipContent.height.toLocaleString() }}</div>
            <div class="tooltip-miner">Mined by: {{ tooltipContent.miner }}</div>
            <div
              v-for="entry in tooltipContent.entries"
              :key="entry.vantage"
              class="tooltip-row"
              :class="{ 'tooltip-winner': entry.isOverallWinner }"
            >
              <span class="tooltip-vantage">{{ formatVantage(entry.vantage) }}</span>
              <span class="tooltip-offset">{{ entry.offset.toFixed(1) }} ms</span>
              <span v-if="entry.isOverallWinner" class="tooltip-badge">★ WINNER</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.pool-detail-view {
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

/* Not found */
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

/* Pool header */
.pool-header {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.pool-identity {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.pool-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.pool-meta-tags {
  display: flex;
  gap: 0.5rem;
}

.tag {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.25rem 0.625rem;
  border-radius: 0.25rem;
}

.tag-type {
  background: rgba(74, 154, 240, 0.15);
  color: var(--accent);
}

.tag-operator {
  background: rgba(52, 211, 153, 0.12);
  color: var(--success);
}

/* Time frame filter */
.timeframe-filter {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.filter-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.frame-buttons {
  display: flex;
  gap: 0.25rem;
}

.frame-buttons button {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  border-radius: 0.25rem;
  border: 1px solid var(--border);
  background: var(--surface-elevated);
  color: var(--text-secondary);
  transition: all 0.15s;
  min-height: 36px;
}

.frame-buttons button:hover:not(:disabled) {
  background: var(--border);
  color: var(--text-primary);
}

.frame-buttons button.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.frame-buttons button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Loading & empty states */
.loading-state,
.no-data-state {
  text-align: center;
  padding: 2rem 1rem;
  color: var(--text-secondary);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  margin-bottom: 1rem;
}

/* Stats grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1rem;
  border-top: 3px solid var(--border);
}

.stat-card-combined {
  border-top-color: var(--accent);
}

.card-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.vantage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--border);
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-name {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.stat-value {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.no-vantage-data {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  font-style: italic;
}

/* Scatter section */
.scatter-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.scatter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.scatter-chart-container {
  width: 100%;
}

/* Vantage legend */
.vantage-legend {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-marker-filled {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--text-secondary);
}

.legend-marker-hollow {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: transparent;
  border: 2px solid var(--text-secondary);
  box-sizing: border-box;
}

/* SVG chart */
.scatter-svg {
  width: 100%;
  height: auto;
  max-height: 350px;
}

.grid-line {
  stroke: var(--border);
  stroke-width: 0.5;
  stroke-dasharray: 3 3;
}

.zero-line {
  stroke: var(--success);
  stroke-width: 1;
  stroke-dasharray: 5 3;
  opacity: 0.5;
}

.axis-label {
  fill: var(--text-primary);
  font-size: 10px;
  font-family: var(--font-mono);
  font-weight: 600;
}

.axis-title {
  fill: var(--text-primary);
  font-size: 11px;
  font-family: var(--font-sans);
  font-weight: 600;
}

.data-point {
  transition: r 0.15s ease;
  cursor: default;
}

.data-point:hover {
  r: 7;
}

/* Custom instant tooltip */
.custom-tooltip {
  position: fixed;
  z-index: 1000;
  background: var(--surface-elevated);
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  pointer-events: none;
  white-space: nowrap;
}

.tooltip-header {
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
  font-size: 0.8125rem;
}

.tooltip-miner {
  font-size: 0.6875rem;
  color: var(--text-secondary);
  margin-bottom: 0.375rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--border);
}

.tooltip-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.125rem 0;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.tooltip-row.tooltip-winner {
  color: var(--accent);
  font-weight: 700;
}

.tooltip-vantage {
  min-width: 80px;
}

.tooltip-offset {
  min-width: 60px;
  text-align: right;
}

.tooltip-badge {
  color: var(--accent);
  font-size: 0.6875rem;
  font-weight: 700;
}

.band-hover {
  cursor: crosshair;
}

/* Responsive */
@media (max-width: 768px) {
  .pool-detail-view {
    padding: 1rem;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .pool-identity {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .timeframe-filter {
    flex-wrap: wrap;
  }

  .vantage-legend {
    gap: 0.5rem;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
