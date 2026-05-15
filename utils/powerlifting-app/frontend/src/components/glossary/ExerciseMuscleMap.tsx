import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { Badge, Box, Group, Paper, SimpleGrid, Stack, Text } from '@mantine/core'
import { BodyChart, ViewSide, type BodyState } from 'body-muscles'
import type { MuscleGroup } from '@powerlifting/types'
import { ALL_MUSCLE_GROUPS, MUSCLE_REGION_MAP } from '@/utils/bodyMuscleRegions'
import { MUSCLE_DISPLAY_NAMES } from '@/utils/muscles'

interface ExerciseMuscleMapProps {
  primary: MuscleGroup[]
  secondary: MuscleGroup[]
  tertiary: MuscleGroup[]
}

const BUCKETS = [
  { key: 'primary', label: 'Primary', color: 'blue', intensity: 10 },
  { key: 'secondary', label: 'Secondary', color: 'cyan', intensity: 6 },
  { key: 'tertiary', label: 'Tertiary', color: 'grape', intensity: 3 },
] as const

function buildBodyState(primary: MuscleGroup[], secondary: MuscleGroup[], tertiary: MuscleGroup[]): BodyState {
  const bodyState: BodyState = {}
  const intensityByMuscle = new Map<MuscleGroup, number>()

  for (const muscle of tertiary) intensityByMuscle.set(muscle, 3)
  for (const muscle of secondary) intensityByMuscle.set(muscle, Math.max(intensityByMuscle.get(muscle) ?? 0, 6))
  for (const muscle of primary) intensityByMuscle.set(muscle, Math.max(intensityByMuscle.get(muscle) ?? 0, 10))

  for (const [muscle, intensity] of intensityByMuscle.entries()) {
    const regions = MUSCLE_REGION_MAP[muscle]
    if (!regions?.length) continue
    for (const region of regions) {
      const currentIntensity = bodyState[region]?.intensity ?? 0
      if (intensity > currentIntensity) {
        bodyState[region] = { intensity, selected: false }
      }
    }
  }

  return bodyState
}

function useBodyChart(containerRef: RefObject<HTMLDivElement | null>, view: ViewSide, bodyState: BodyState, ariaLabel: string) {
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
      if (chartRef.current === chart) chartRef.current = null
    }
  }, [ariaLabel, containerRef, view])

  useEffect(() => {
    chartRef.current?.update({ bodyState })
  }, [bodyState])
}

function bucketFor(muscle: MuscleGroup, primary: MuscleGroup[], secondary: MuscleGroup[], tertiary: MuscleGroup[]) {
  if (primary.includes(muscle)) return BUCKETS[0]
  if (secondary.includes(muscle)) return BUCKETS[1]
  if (tertiary.includes(muscle)) return BUCKETS[2]
  return null
}

export function ExerciseMuscleMap({ primary, secondary, tertiary }: ExerciseMuscleMapProps) {
  const frontRef = useRef<HTMLDivElement | null>(null)
  const backRef = useRef<HTMLDivElement | null>(null)
  const bodyState = useMemo(() => buildBodyState(primary, secondary, tertiary), [primary, secondary, tertiary])
  const selectedMuscles = useMemo(
    () =>
      ALL_MUSCLE_GROUPS
        .map((muscle) => ({ muscle, bucket: bucketFor(muscle, primary, secondary, tertiary) }))
        .filter((row): row is { muscle: MuscleGroup; bucket: typeof BUCKETS[number] } => row.bucket !== null),
    [primary, secondary, tertiary]
  )

  useBodyChart(frontRef, ViewSide.FRONT, bodyState, 'Anterior exercise muscle map')
  useBodyChart(backRef, ViewSide.BACK, bodyState, 'Posterior exercise muscle map')

  return (
    <Paper withBorder p="md">
      <Stack gap="md">
        <Group justify="space-between" align="center" wrap="wrap">
          <Text size="sm" fw={600}>Muscle Map</Text>
          <Group gap="xs">
            {BUCKETS.map((bucket) => (
              <Badge key={bucket.key} color={bucket.color} variant="light" size="sm">{bucket.label}</Badge>
            ))}
          </Group>
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <Box>
            <Text size="xs" c="dimmed" ta="center" mb={4}>Front</Text>
            <Box
              ref={frontRef}
              style={{
                minHeight: 260,
                borderRadius: 'var(--mantine-radius-sm)',
                background: 'linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.02))',
              }}
            />
          </Box>
          <Box>
            <Text size="xs" c="dimmed" ta="center" mb={4}>Back</Text>
            <Box
              ref={backRef}
              style={{
                minHeight: 260,
                borderRadius: 'var(--mantine-radius-sm)',
                background: 'linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.02))',
              }}
            />
          </Box>
        </SimpleGrid>

        {selectedMuscles.length ? (
          <Group gap={6}>
            {selectedMuscles.map(({ muscle, bucket }) => (
              <Badge key={muscle} color={bucket.color} variant="light" size="sm">
                {MUSCLE_DISPLAY_NAMES[muscle]}
              </Badge>
            ))}
          </Group>
        ) : (
          <Text size="sm" c="dimmed">Select muscles to preview the movement map.</Text>
        )}
      </Stack>
    </Paper>
  )
}
