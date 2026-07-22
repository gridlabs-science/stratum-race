import { describe, expect, it } from 'vitest'
import type { RaceResult } from '@/types'
import { buildUnifiedTimeline } from './blockTimeline'

function race(overrides: Partial<RaceResult> = {}): RaceResult {
  return {
    version: 1,
    vantage: 'main-dc',
    block_height: 900000,
    prevhash: '00'.repeat(32),
    prevhash_short: '...test',
    first_epoch: 1000,
    first_utc: '1970-01-01T00:16:40Z',
    confirm_window_s: 15,
    winner: 'public-fast',
    winner_nonempty: 'public-fast',
    block_miner: 'test',
    block_miner_source: 'test',
    arrivals_offset_ms: {
      'public-fast': 0,
      'local-sv1': 300,
      'local-sv2': 450,
    },
    nonempty_arrivals_offset_ms: {
      'public-fast': 0,
      'local-sv1': 350,
    },
    empty_first_pools: ['local-sv1'],
    empty_to_full_ms: { 'local-sv1': 50 },
    missed_pools: ['public-missed'],
    eligible_at_start: ['public-fast', 'public-missed', 'local-sv1', 'local-sv2'],
    pools_connected: 4,
    pools_eligible: 4,
    pool_protocols: {
      'public-fast': 'sv1',
      'public-missed': 'sv1',
      'local-sv1': 'sv1',
      'local-sv2': 'sv2',
    },
    pool_cohorts: {
      'public-fast': 'public-reference',
      'public-missed': 'public-reference',
      'local-sv1': 'gridpool-local',
      'local-sv2': 'gridpool-local',
    },
    template_observability: {
      'public-fast': 'sv1-merkle-branch',
      'public-missed': 'sv1-merkle-branch',
      'local-sv1': 'sv1-merkle-branch',
      'local-sv2': 'opaque',
    },
    collector_meta: { version: 'test', uptime_seconds: 1, session_races: 1 },
    ...overrides,
  }
}

describe('buildUnifiedTimeline', () => {
  it('anchors the axis to the earliest event regardless of event type', () => {
    const result = buildUnifiedTimeline(race({
      gridpool_chain_tip: {
        available: true,
        first_peer_header: {
          timestamp_utc: '1970-01-01T00:16:39.900Z',
          epoch_ms: 999900,
          transport: 'udp',
        },
        local_node: {
          timestamp_utc: '1970-01-01T00:16:40.100Z',
          epoch_ms: 1000100,
          transport: 'bitcoin-zmq-rawblock',
        },
      },
    }))

    expect(result.startEpochMs).toBe(999900)
    const protocol = result.groups.find((group) => group.category === 'protocol')!
    const peer = protocol.rows.find((row) => row.id === 'protocol-peer-header')!
    expect(peer.markers[0].offsetMs).toBe(0)
    const publicGroup = result.groups.find((group) => group.category === 'public')!
    expect(publicGroup.rows[0].markers[0].offsetMs).toBe(100)
  })

  it('separates public and local endpoints and retains missing rows', () => {
    const result = buildUnifiedTimeline(race())
    const publicGroup = result.groups.find((group) => group.category === 'public')!
    const localGroup = result.groups.find((group) => group.category === 'local')!

    expect(publicGroup.rows.map((row) => row.label)).toEqual(['public-fast', 'public-missed'])
    expect(publicGroup.rows[1].status).toBe('missing')
    expect(localGroup.rows.map((row) => row.label)).toEqual(['local-sv1', 'local-sv2'])
  })

  it('shows empty-first SV1 work and opaque SV2 work without calling SV2 full', () => {
    const result = buildUnifiedTimeline(race())
    const localGroup = result.groups.find((group) => group.category === 'local')!
    const sv1 = localGroup.rows.find((row) => row.label === 'local-sv1')!
    const sv2 = localGroup.rows.find((row) => row.label === 'local-sv2')!

    expect(sv1.markers.map((marker) => marker.kind)).toEqual(['empty', 'full'])
    expect(sv2.markers).toHaveLength(1)
    expect(sv2.markers[0].kind).toBe('opaque')
    expect(sv2.markers[0].label).toContain('opaque')
  })

  it('keeps protocol rows visible when GridPool telemetry is absent', () => {
    const result = buildUnifiedTimeline(race())
    const protocol = result.groups.find((group) => group.category === 'protocol')!

    expect(protocol.rows).toHaveLength(4)
    expect(protocol.rows.every((row) => row.status === 'missing')).toBe(true)
  })
})
