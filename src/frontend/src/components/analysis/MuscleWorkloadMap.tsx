import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Anchor, Badge, Box, Group, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core'
import { BodyChart, ViewSide, type BodyState, type MuscleId } from 'body-muscles'
import type { MuscleGroup } from '@powerlifting/types'
import type { MuscleLandmarks, MuscleVolume, MuscleVolumeStatus } from '@/api/analytics'
import { MUSCLE_DISPLAY_NAMES } from '@/utils/muscles'
import { ALL_MUSCLE_GROUPS, MUSCLE_REGION_MAP } from '@/utils/bodyMuscleRegions'
import { ChartHelp } from '@/components/analysis/ChartHelp'

type Band = {
  label: string
  badgeColor: string
  intensity: number
  color: string
}

const NEUTRAL: Band = { label: 'Unrated', badgeColor: 'gray', intensity: 0, color: '#94a3b8' }

const STATUS_BANDS: Record<MuscleVolumeStatus, Band> = {
  unrated: NEUTRAL,
  below_mev: { label: 'Below MEV', badgeColor: 'yellow', intensity: 2, color: '#facc15' },
  productive: { label: 'Productive', badgeColor: 'orange', intensity: 5, color: '#f97316' },
  near_mrv: { label: 'Near MRV', badgeColor: 'red', intensity: 8, color: '#dc2626' },
  above_mrv: { label: 'Above MRV', badgeColor: 'dark', intensity: 10, color: '#7f1d1d' },
}

const NO_WORK: Band = { label: 'No work', badgeColor: 'gray', intensity: 0, color: '#94a3b8' }

const LEGACY_LEGEND = [
  { label: 'None', color: '#94a3b8' },
  { label: 'Light <4', color: '#facc15' },
  { label: 'Moderate 4-7.9', color: '#f97316' },
  { label: 'Heavy 8-11.9', color: '#dc2626' },
  { label: 'Very Heavy 12+', color: '#7f1d1d' },
]

const LANDMARK_LEGEND = [
  { label: 'Unrated / no work', color: NEUTRAL.color },
  { label: 'Below MEV', color: STATUS_BANDS.below_mev.color },
  { label: 'MEV to MAV high (productive)', color: STATUS_BANDS.productive.color },
  { label: 'MAV high to MRV', color: STATUS_BANDS.near_mrv.color },
  { label: 'Above MRV', color: STATUS_BANDS.above_mrv.color },
]

interface MapRow {
  muscle: MuscleGroup
  sets: number
  band: Band
  landmarks: MuscleLandmarks | null
}

interface MuscleWorkloadMapProps {
  setsPerWeek?: Partial<Record<MuscleGroup, number>>
  muscleVolume?: MuscleVolume | null
  analysisWeeks: number
  title?: string
  subtitle?: string
}

function legacyBand(setsPerWeek: number): Band {
  if (setsPerWeek <= 0) return { label: 'None', badgeColor: 'gray', intensity: 0, color: '#94a3b8' }
  if (setsPerWeek < 4) return { label: 'Light', badgeColor: 'yellow', intensity: 2, color: '#facc15' }
  if (setsPerWeek < 8) return { label: 'Moderate', badgeColor: 'orange', intensity: 5, color: '#f97316' }
  if (setsPerWeek < 12) return { label: 'Heavy', badgeColor: 'red', intensity: 8, color: '#dc2626' }
  return { label: 'Very Heavy', badgeColor: 'dark', intensity: 10, color: '#7f1d1d' }
}

function landmarkBand(sets: number, status: MuscleVolumeStatus): Band {
  if (status === 'unrated') return NEUTRAL
  if (sets <= 0) return NO_WORK
  return STATUS_BANDS[status]
}

function formatRange(landmarks: MuscleLandmarks): string {
  return `MEV ${landmarks.mev} · MAV ${landmarks.mav_low}-${landmarks.mav_high} · MRV ${landmarks.mrv}`
}

function buildRows({ setsPerWeek, muscleVolume }: Pick<MuscleWorkloadMapProps, 'setsPerWeek' | 'muscleVolume'>): MapRow[] {
  return ALL_MUSCLE_GROUPS.map((muscle) => {
    const entry = muscleVolume?.muscles[muscle]
    if (muscleVolume) {
      const sets = entry?.weekly_sets ?? 0
      return { muscle, sets, band: landmarkBand(sets, entry?.status ?? 'unrated'), landmarks: entry?.landmarks ?? null }
    }
    const sets = setsPerWeek?.[muscle] ?? 0
    return { muscle, sets, band: legacyBand(sets), landmarks: null }
  }).sort((a, b) => b.sets - a.sets || MUSCLE_DISPLAY_NAMES[a.muscle].localeCompare(MUSCLE_DISPLAY_NAMES[b.muscle]))
}

function buildBodyState(rows: MapRow[]): BodyState {
  const bodyState: BodyState = {}
  for (const { muscle, band } of rows) {
    const regions = MUSCLE_REGION_MAP[muscle]
    if (!regions?.length || band.intensity <= 0) continue
    for (const region of regions) {
      const currentIntensity = bodyState[region]?.intensity ?? 0
      if (band.intensity > currentIntensity) {
        bodyState[region] = { intensity: band.intensity, selected: false }
      }
    }
  }
  return bodyState
}

function useBodyChart(
  containerRef: RefObject<HTMLDivElement | null>,
  view: ViewSide,
  bodyState: BodyState,
  ariaLabel: string,
  onHover: (id: MuscleId | null) => void
) {
  const chartRef = useRef<BodyChart | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = new BodyChart(containerRef.current, {
      view,
      bodyState,
      ariaLabel,
      enableTransitions: true,
      onMuscleHover: onHover,
    })

    chartRef.current = chart
    return () => {
      chart.destroy()
      if (chartRef.current === chart) {
        chartRef.current = null
      }
    }
  }, [ariaLabel, containerRef, view, onHover])

  useEffect(() => {
    chartRef.current?.update({ bodyState })
  }, [bodyState])
}

function describeRow(row: MapRow): string {
  const base = `${MUSCLE_DISPLAY_NAMES[row.muscle]}: ${row.sets.toFixed(1)} sets/wk, ${row.band.label}`
  return row.landmarks ? `${base} (${formatRange(row.landmarks)})` : base
}

export function MuscleWorkloadMap({
  setsPerWeek,
  muscleVolume,
  analysisWeeks,
  title = 'Muscle Workload Map',
  subtitle,
}: MuscleWorkloadMapProps) {
  const frontRef = useRef<HTMLDivElement | null>(null)
  const backRef = useRef<HTMLDivElement | null>(null)
  const [hovered, setHovered] = useState<MuscleId | null>(null)
  const onHover = useCallback((id: MuscleId | null) => setHovered(id), [])

  const rows = useMemo(() => buildRows({ setsPerWeek, muscleVolume }), [setsPerWeek, muscleVolume])
  const bodyState = useMemo(() => buildBodyState(rows), [rows])
  const hasWorkload = rows.some((row) => row.sets > 0)
  const hoveredRow = useMemo(() => {
    if (!hovered) return null
    return rows
      .filter((row) => MUSCLE_REGION_MAP[row.muscle]?.includes(hovered))
      .sort((a, b) => b.band.intensity - a.band.intensity)[0] ?? null
  }, [hovered, rows])
  const landmarkMode = Boolean(muscleVolume)

  useBodyChart(frontRef, ViewSide.FRONT, bodyState, 'Anterior muscle workload map', onHover)
  useBodyChart(backRef, ViewSide.BACK, bodyState, 'Posterior muscle workload map', onHover)

  if (!hasWorkload) {
    return (
      <Stack gap="xs">
        <Text fw={500}>{title}</Text>
        <Text size="sm" c="dimmed">
          No glossary matches were found for this session.
        </Text>
      </Stack>
    )
  }

  const weeks = muscleVolume?.weeks ?? analysisWeeks
  const resolvedSubtitle = subtitle ?? `Average weighted sets per week across ${weeks} week${weeks === 1 ? '' : 's'}`

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Text fw={500}>{title}</Text>
        <Text size="xs" c="dimmed">{resolvedSubtitle}</Text>
      </Group>

      {landmarkMode && (
        <ChartHelp
          mb="0"
          description="Average weekly sets per muscle (primary 1.0, secondary 0.5, tertiary 0.25) compared with that muscle's own researched volume landmarks. Landmarks are hypertrophy guidelines, so read them as a guide to accessory volume, not a target."
          range="MEV is the least volume that still builds muscle, MAV the productive range, MRV the most you can recover from. Each muscle has its own numbers (see the list)."
          units="weighted sets per muscle per week"
          relation="Colour is the status against each muscle's own range, so 10 sets can be productive for one muscle and above MRV for another."
        />
      )}

      <SimpleGrid cols={{ base: 1, xl: 3 }} spacing="lg">
        <Box>
          <Text size="xs" c="dimmed" ta="center" mb="xs">Front</Text>
          <Box
            ref={frontRef}
            style={{
              minHeight: 360,
              borderRadius: 'var(--mantine-radius-sm)',
              background: 'linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.02))',
            }}
          />
        </Box>

        <Box>
          <Text size="xs" c="dimmed" ta="center" mb="xs">Back</Text>
          <Box
            ref={backRef}
            style={{
              minHeight: 360,
              borderRadius: 'var(--mantine-radius-sm)',
              background: 'linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.02))',
            }}
          />
        </Box>

        <Stack gap={0}>
          <Text size="xs" c="dimmed" mb="xs" mih={32}>
            {hoveredRow ? describeRow(hoveredRow) : 'Average weighted sets per week. Hover a muscle for its range.'}
          </Text>
          {rows.map((row) => {
            const entry = (
              <Group
                key={row.muscle}
                justify="space-between"
                align="center"
                py={7}
                style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}
              >
                <Stack gap={0}>
                  <Text size="sm" fw={500}>{MUSCLE_DISPLAY_NAMES[row.muscle]}</Text>
                  {row.landmarks && <Text size="xs" c="dimmed">{formatRange(row.landmarks)}</Text>}
                </Stack>
                <Group gap="xs" wrap="nowrap">
                  <Badge variant="light" color={row.band.badgeColor} size="sm">{row.band.label}</Badge>
                  <Text size="sm" fw={600} w={68} ta="right">{row.sets.toFixed(1)}/wk</Text>
                </Group>
              </Group>
            )
            return row.landmarks ? (
              <Tooltip key={row.muscle} label={`${row.landmarks.basis.replace(/_/g, ' ')} landmarks; MV ${row.landmarks.mv}`} withArrow>
                {entry}
              </Tooltip>
            ) : entry
          })}
        </Stack>
      </SimpleGrid>

      <Group gap="sm" wrap="wrap">
        {(landmarkMode ? LANDMARK_LEGEND : LEGACY_LEGEND).map((item) => (
          <Group key={item.label} gap={6} wrap="nowrap">
            <Box
              style={{
                width: 10,
                height: 10,
                borderRadius: 999,
                background: item.color,
                flexShrink: 0,
              }}
            />
            <Text size="xs" c="dimmed">{item.label}</Text>
          </Group>
        ))}
      </Group>

      {muscleVolume && muscleVolume.sources.length > 0 && (
        <Group gap="xs" wrap="wrap">
          <Text size="xs" c="dimmed">Landmark sources:</Text>
          {muscleVolume.sources.map((source) => (
            <Tooltip key={source.id} label={source.note ?? source.citation} withArrow multiline w={320}>
              <Anchor href={source.url} target="_blank" rel="noreferrer" size="xs">
                {source.id.replace(/_/g, ' ')}
              </Anchor>
            </Tooltip>
          ))}
        </Group>
      )}
    </Stack>
  )
}
