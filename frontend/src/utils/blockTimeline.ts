import type { ChainTipEvent, RaceResult } from '@/types'

export type TimelineCategory = 'public' | 'protocol' | 'local' | 'other'
export type TimelineMarkerKind = 'full' | 'empty' | 'opaque' | 'peer' | 'node' | 'snapshot' | 'relay' | 'synthetic'

export interface UnifiedTimelineMarker {
  kind: TimelineMarkerKind
  label: string
  epochMs: number
  offsetMs: number
  transport?: string
  source?: string
}

export interface UnifiedTimelineRow {
  id: string
  label: string
  category: TimelineCategory
  status: 'observed' | 'missing'
  markers: UnifiedTimelineMarker[]
  sortEpochMs: number
}

export interface UnifiedTimelineGroup {
  category: TimelineCategory
  label: string
  rows: UnifiedTimelineRow[]
}

export interface UnifiedVantageTimeline {
  vantage: string
  startEpochMs: number
  endEpochMs: number
  durationMs: number
  groups: UnifiedTimelineGroup[]
}

const GROUPS: Array<{ category: TimelineCategory; label: string }> = [
  { category: 'public', label: 'Public endpoints' },
  { category: 'protocol', label: 'Node and GridPool events' },
  { category: 'local', label: 'Local endpoints' },
  { category: 'other', label: 'Other endpoints' },
]

function endpointCategory(cohort?: string): TimelineCategory {
  if (cohort === 'public-reference') return 'public'
  if (cohort === 'gridpool-local') return 'local'
  return 'other'
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function eventMarker(
  event: ChainTipEvent | null | undefined,
  kind: TimelineMarkerKind,
  label: string,
): UnifiedTimelineMarker | null {
  if (!event || !Number.isFinite(event.epoch_ms)) return null
  return {
    kind,
    label,
    epochMs: event.epoch_ms,
    offsetMs: 0,
    transport: event.transport,
    source: event.source,
  }
}

function protocolRow(
  id: string,
  label: string,
  marker: UnifiedTimelineMarker | null,
): UnifiedTimelineRow {
  return {
    id,
    label,
    category: 'protocol',
    status: marker ? 'observed' : 'missing',
    markers: marker ? [marker] : [],
    sortEpochMs: marker?.epochMs ?? Number.POSITIVE_INFINITY,
  }
}

export function buildUnifiedTimeline(race: RaceResult): UnifiedVantageTimeline {
  const endpointNames = new Set<string>([
    ...Object.keys(race.pool_cohorts ?? {}),
    ...Object.keys(race.pool_protocols ?? {}),
    ...Object.keys(race.arrivals_offset_ms ?? {}),
    ...Object.keys(race.nonempty_arrivals_offset_ms ?? {}),
  ])
  const firstEpochMs = race.first_epoch * 1000
  const absoluteWorkArrivals = race.gridpool_chain_tip?.work_arrival_epoch_ms ?? {}
  const endpointRows: UnifiedTimelineRow[] = []

  for (const pool of endpointNames) {
    const category = endpointCategory(race.pool_cohorts?.[pool])
    const protocol = race.pool_protocols?.[pool]
    const observability = race.template_observability?.[pool]
    const anyOffset = race.arrivals_offset_ms?.[pool]
    const fullOffset = race.nonempty_arrivals_offset_ms?.[pool]
    const isEmptyFirst = race.empty_first_pools?.includes(pool) ?? false
    const markers: UnifiedTimelineMarker[] = []
    const absoluteArrival = absoluteWorkArrivals[pool]
    const arrivalEpochMs = (offset: number) =>
      isFiniteNumber(absoluteArrival) ? absoluteArrival : firstEpochMs + offset

    if (isEmptyFirst && isFiniteNumber(anyOffset)) {
      markers.push({
        kind: 'empty',
        label: 'Initial empty work',
        epochMs: arrivalEpochMs(anyOffset),
        offsetMs: 0,
      })
    }
    if (isFiniteNumber(fullOffset)) {
      markers.push({
        kind: 'full',
        label: 'Final full work',
        epochMs: isFiniteNumber(absoluteArrival)
          ? absoluteArrival + Math.max(0, fullOffset - (anyOffset ?? fullOffset))
          : firstEpochMs + fullOffset,
        offsetMs: 0,
      })
    } else if (protocol === 'sv2' || observability === 'opaque') {
      if (isFiniteNumber(anyOffset)) {
        markers.push({
          kind: 'opaque',
          label: 'Miner-usable SV2 job (opaque)',
          epochMs: arrivalEpochMs(anyOffset),
          offsetMs: 0,
        })
      }
    } else if (!isEmptyFirst && isFiniteNumber(anyOffset)) {
      markers.push({
        kind: 'full',
        label: 'Miner-facing work',
        epochMs: arrivalEpochMs(anyOffset),
        offsetMs: 0,
      })
    }

    endpointRows.push({
      id: `endpoint-${pool}`,
      label: pool,
      category,
      status: markers.some((marker) => marker.kind === 'full' || marker.kind === 'opaque')
        ? 'observed'
        : 'missing',
      markers,
      sortEpochMs: markers.length
        ? Math.min(...markers.map((marker) => marker.epochMs))
        : Number.POSITIVE_INFINITY,
    })
  }

  const tip = race.gridpool_chain_tip
  const peerMarker = eventMarker(
    tip?.first_peer_header,
    'peer',
    'Inbound peer header',
  )
  const fastestLocalRow = endpointRows
    .filter((row) => row.category === 'local' && row.status === 'observed')
    .sort((left, right) => left.sortEpochMs - right.sortEpochMs)[0]
  const syntheticMarker = peerMarker && fastestLocalRow
    ? {
        ...peerMarker,
        kind: 'synthetic' as const,
        label: `Modeled ${fastestLocalRow.label} work at peer-tip arrival`,
        source: fastestLocalRow.label,
      }
    : null
  const protocolRows = [
    protocolRow(
      'protocol-peer-header',
      'GridPool peer chain-tip notification',
      peerMarker,
    ),
    protocolRow(
      'protocol-local-node',
      'Local Bitcoin node notification',
      eventMarker(tip?.local_node ?? tip?.local_zmq, 'node', 'Local node notification'),
    ),
    protocolRow(
      'protocol-local-header',
      'Local raw block header available',
      eventMarker(tip?.local_header, 'node', 'Raw header available'),
    ),
    protocolRow(
      'protocol-snapshot',
      'GridPool payout snapshot',
      eventMarker(tip?.payout_snapshot, 'snapshot', 'Snapshot activated'),
    ),
    protocolRow(
      'protocol-relay',
      'GridPool chain-tip relay dispatch',
      eventMarker(tip?.relay_dispatch, 'relay', 'UDP/WebSocket dispatch'),
    ),
    protocolRow(
      'protocol-synthetic-fast-gridpool',
      'Synthetic Fast GridPool',
      syntheticMarker,
    ),
  ]

  const allRows = [...endpointRows, ...protocolRows]
  const allMarkers = allRows.flatMap((row) => row.markers)
  const startEpochMs = allMarkers.length
    ? Math.min(...allMarkers.map((marker) => marker.epochMs))
    : firstEpochMs
  const endEpochMs = allMarkers.length
    ? Math.max(...allMarkers.map((marker) => marker.epochMs))
    : firstEpochMs

  for (const marker of allMarkers) {
    marker.offsetMs = marker.epochMs - startEpochMs
  }

  const groups = GROUPS
    .map(({ category, label }) => ({
      category,
      label,
      rows: allRows
        .filter((row) => row.category === category)
        .sort((left, right) => left.sortEpochMs - right.sortEpochMs || left.label.localeCompare(right.label)),
    }))
    .filter((group) => group.category === 'protocol' || group.rows.length > 0)

  return {
    vantage: race.vantage,
    startEpochMs,
    endEpochMs,
    durationMs: Math.max(endEpochMs - startEpochMs, 1),
    groups,
  }
}

export function buildSynchronizedTimelines(races: RaceResult[]): UnifiedVantageTimeline[] {
  const timelines = races.map(buildUnifiedTimeline)
  const observed = timelines.filter((timeline) =>
    timeline.groups.some((group) => group.rows.some((row) => row.markers.length > 0)),
  )
  if (observed.length === 0) return timelines

  const globalStartEpochMs = Math.min(...observed.map((timeline) => timeline.startEpochMs))
  const globalEndEpochMs = Math.max(...observed.map((timeline) => timeline.endEpochMs))
  const durationMs = Math.max(globalEndEpochMs - globalStartEpochMs, 1)

  for (const timeline of timelines) {
    timeline.startEpochMs = globalStartEpochMs
    timeline.endEpochMs = globalEndEpochMs
    timeline.durationMs = durationMs
    for (const marker of timeline.groups.flatMap((group) => group.rows.flatMap((row) => row.markers))) {
      marker.offsetMs = marker.epochMs - globalStartEpochMs
    }
  }
  return timelines
}
