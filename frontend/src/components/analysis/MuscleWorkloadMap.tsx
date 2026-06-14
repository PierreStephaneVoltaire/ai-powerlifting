import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { Badge, Box, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { BodyChart, ViewSide, type BodyState } from 'body-muscles'
import type { MuscleGroup } from '@powerlifting/types'
import { MUSCLE_DISPLAY_NAMES } from '@/utils/muscles'
import { ALL_MUSCLE_GROUPS, MUSCLE_REGION_MAP } from '@/utils/bodyMuscleRegions'

const LEGEND_ITEMS = [
  { label: 'None', color: '#94a3b8' },
  { label: 'Light <4', color: '#facc15' },
  { label: 'Moderate 4-7.9', color: '#f97316' },
  { label: 'Heavy 8-11.9', color: '#dc2626' },
  { label: 'Very Heavy 12+', color: '#7f1d1d' },
]

type WorkloadBand = {
  label: string
  badgeColor: string
  intensity: number
}

interface MuscleWorkloadMapProps {
  setsPerWeek: Partial<Record<MuscleGroup, number>>
  analysisWeeks: number
  title?: string
  subtitle?: string
}

function getWorkloadBand(setsPerWeek: number): WorkloadBand {
  if (setsPerWeek <= 0) return { label: 'None', badgeColor: 'gray', intensity: 0 }
  if (setsPerWeek < 4) return { label: 'Light', badgeColor: 'yellow', intensity: 2 }
  if (setsPerWeek < 8) return { label: 'Moderate', badgeColor: 'orange', intensity: 5 }
  if (setsPerWeek < 12) return { label: 'Heavy', badgeColor: 'red', intensity: 8 }
  return { label: 'Very Heavy', badgeColor: 'dark', intensity: 10 }
}

function buildBodyState(setsPerWeek: Partial<Record<MuscleGroup, number>>): BodyState {
  const bodyState: BodyState = {}

  for (const muscle of ALL_MUSCLE_GROUPS) {
    const regions = MUSCLE_REGION_MAP[muscle]
    if (!regions?.length) continue

    const intensity = getWorkloadBand(setsPerWeek[muscle] ?? 0).intensity
    if (intensity <= 0) continue

    for (const region of regions) {
      const currentIntensity = bodyState[region]?.intensity ?? 0
      if (intensity > currentIntensity) {
        bodyState[region] = { intensity, selected: false }
      }
    }
  }

  return bodyState
}

function useBodyChart(
  containerRef: RefObject<HTMLDivElement | null>,
  view: ViewSide,
  bodyState: BodyState,
  ariaLabel: string
) {
  const chartRef = useRef<BodyChart | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = new BodyChart(containerRef.current, {
      view,
      bodyState,
      ariaLabel,
      enableTransitions: true,
    })

    chartRef.current = chart
    return () => {
      chart.destroy()
      if (chartRef.current === chart) {
        chartRef.current = null
      }
    }
  }, [ariaLabel, containerRef, view])

  useEffect(() => {
    chartRef.current?.update({ bodyState })
  }, [bodyState])
}

export function MuscleWorkloadMap({ setsPerWeek, analysisWeeks, title = 'Muscle Workload Map', subtitle }: MuscleWorkloadMapProps) {
  const frontRef = useRef<HTMLDivElement | null>(null)
  const backRef = useRef<HTMLDivElement | null>(null)

  const bodyState = useMemo(() => buildBodyState(setsPerWeek), [setsPerWeek])
  const rankedMuscles = useMemo(
    () =>
      ALL_MUSCLE_GROUPS
        .map((muscle) => ({ muscle, sets: setsPerWeek[muscle] ?? 0, band: getWorkloadBand(setsPerWeek[muscle] ?? 0) }))
        .sort((a, b) => b.sets - a.sets || MUSCLE_DISPLAY_NAMES[a.muscle].localeCompare(MUSCLE_DISPLAY_NAMES[b.muscle])),
    [setsPerWeek]
  )
  const hasWorkload = rankedMuscles.some((row) => row.sets > 0)

  useBodyChart(frontRef, ViewSide.FRONT, bodyState, 'Anterior muscle workload map')
  useBodyChart(backRef, ViewSide.BACK, bodyState, 'Posterior muscle workload map')

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

  const resolvedSubtitle = subtitle ?? `Weighted sets per week across ${analysisWeeks} week${analysisWeeks === 1 ? '' : 's'}`

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Text fw={500}>{title}</Text>
        <Text size="xs" c="dimmed">{resolvedSubtitle}</Text>
      </Group>

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
          <Text size="xs" c="dimmed" mb="xs">Exact weighted sets per week</Text>
          {rankedMuscles.map(({ muscle, sets, band }) => (
            <Group
              key={muscle}
              justify="space-between"
              align="center"
              py={7}
              style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}
            >
              <Text size="sm" fw={500}>{MUSCLE_DISPLAY_NAMES[muscle]}</Text>
              <Group gap="xs" wrap="nowrap">
                <Badge variant="light" color={band.badgeColor} size="sm">{band.label}</Badge>
                <Text size="sm" fw={600} w={68} ta="right">{sets.toFixed(1)}/wk</Text>
              </Group>
            </Group>
          ))}
        </Stack>
      </SimpleGrid>

      <Group gap="sm" wrap="wrap">
        {LEGEND_ITEMS.map((item) => (
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
    </Stack>
  )
}
