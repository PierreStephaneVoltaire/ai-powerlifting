import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Box, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { BodyChart, ViewSide, type BodyState, type MuscleId } from 'body-muscles'
import type { MuscleGroup } from '@powerlifting/types'
import type { MuscleVolume, MuscleVolumeStatus } from '@/api/analytics'
import { ChartLabel } from '@/components/analysis/ChartLabel'
import { MUSCLE_DISPLAY_NAMES } from '@/utils/muscles'
import { ALL_MUSCLE_GROUPS, MUSCLE_REGION_MAP } from '@/utils/bodyMuscleRegions'

const STATUS_INTENSITY: Record<MuscleVolumeStatus, number> = {
  unrated: 0,
  below_mev: 2,
  productive: 5,
  near_mrv: 8,
  above_mrv: 10,
}

const LEGEND = [
  { label: 'Below MEV', color: '#facc15' },
  { label: 'MEV-MAV', color: '#f97316' },
  { label: 'MAV-MRV', color: '#dc2626' },
  { label: 'Above MRV', color: '#7f1d1d' },
]

interface Row {
  muscle: MuscleGroup
  sets: number
  range: string | null
  intensity: number
}

function buildRows(volume: MuscleVolume): Row[] {
  return ALL_MUSCLE_GROUPS.map((muscle) => {
    const entry = volume.muscles?.[muscle]
    const landmarks = entry?.landmarks ?? null
    const sets = entry?.weekly_sets ?? 0
    return {
      muscle,
      sets,
      range: landmarks ? `MEV\u2013MRV ${landmarks.mev}\u2013${landmarks.mrv}` : null,
      intensity: entry && sets > 0 ? STATUS_INTENSITY[entry.status] ?? 0 : 0,
    }
  })
}

function buildBodyState(rows: Row[]): BodyState {
  const state: BodyState = {}
  for (const { muscle, intensity } of rows) {
    const regions = MUSCLE_REGION_MAP[muscle]
    if (!regions?.length || intensity <= 0) continue
    for (const region of regions) {
      if (intensity > (state[region]?.intensity ?? 0)) state[region] = { intensity, selected: false }
    }
  }
  return state
}

function useBodyChart(
  containerRef: RefObject<HTMLDivElement | null>,
  view: ViewSide,
  bodyState: BodyState,
  ariaLabel: string,
  onHover: (id: MuscleId | null) => void,
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
      if (chartRef.current === chart) chartRef.current = null
    }
  }, [ariaLabel, containerRef, view, onHover])

  useEffect(() => {
    chartRef.current?.update({ bodyState })
  }, [bodyState])
}

const PANEL_STYLE = {
  minHeight: 360,
  borderRadius: 'var(--mantine-radius-sm)',
  background: 'linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.02))',
}

export function MuscleVolumeMap({ volume, title = 'Avg Weekly Sets by Muscle' }: { volume: MuscleVolume; title?: string }) {
  const frontRef = useRef<HTMLDivElement | null>(null)
  const backRef = useRef<HTMLDivElement | null>(null)
  const [hovered, setHovered] = useState<MuscleId | null>(null)
  const onHover = useCallback((id: MuscleId | null) => setHovered(id), [])

  const rows = useMemo(() => buildRows(volume), [volume])
  const bodyState = useMemo(() => buildBodyState(rows), [rows])
  const hoveredRow = useMemo(() => {
    if (!hovered) return null
    return rows
      .filter((row) => MUSCLE_REGION_MAP[row.muscle]?.includes(hovered))
      .sort((a, b) => b.intensity - a.intensity || b.sets - a.sets)[0] ?? null
  }, [hovered, rows])

  useBodyChart(frontRef, ViewSide.FRONT, bodyState, 'Anterior weekly sets by muscle', onHover)
  useBodyChart(backRef, ViewSide.BACK, bodyState, 'Posterior weekly sets by muscle', onHover)

  return (
    <Stack gap="sm">
      <Text fw={500}>{title}</Text>
      <ChartLabel text="Average weekly sets per muscle, against its researched range." formulaId="volume_landmarks" mb="0" />
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
        <Box>
          <Text size="xs" c="dimmed" ta="center" mb="xs">Front</Text>
          <Box ref={frontRef} style={PANEL_STYLE} />
        </Box>
        <Box>
          <Text size="xs" c="dimmed" ta="center" mb="xs">Back</Text>
          <Box ref={backRef} style={PANEL_STYLE} />
        </Box>
      </SimpleGrid>
      <Text size="xs" mih={18}>
        {hoveredRow
          ? `${MUSCLE_DISPLAY_NAMES[hoveredRow.muscle]} · ${hoveredRow.sets.toFixed(1)} sets/wk${hoveredRow.range ? ` · ${hoveredRow.range}` : ''}`
          : ''}
      </Text>
      <Group gap="sm" wrap="wrap">
        {LEGEND.map((item) => (
          <Group key={item.label} gap={6} wrap="nowrap">
            <Box style={{ width: 10, height: 10, borderRadius: 999, background: item.color, flexShrink: 0 }} />
            <Text size="xs" c="dimmed">{item.label}</Text>
          </Group>
        ))}
      </Group>
    </Stack>
  )
}
