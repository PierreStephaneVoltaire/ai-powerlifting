import { useMemo, useState } from 'react'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import {
  calculateDots,
  calculateDotsFromLifts,
  totalForTargetDots,
  dotsAcrossWeightClasses,
  getDotsLevel,
} from '@/utils/dots'
import { displayWeight, kgToLb, toDisplayUnit } from '@/utils/units'
import {
  Paper,
  Button,
  Group,
  Stack,
  SimpleGrid,
  TextInput,
  Table,
  Text,
  Title,
  SegmentedControl,
} from '@mantine/core'
import type { Sex } from '@powerlifting/types'

export default function DotsCalculator() {
  const { sex, unit } = useSettingsStore()
  const { program } = useProgramStore()

  const [squatKg, setSquatKg] = useState<number>(0)
  const [benchKg, setBenchKg] = useState<number>(0)
  const [deadliftKg, setDeadliftKg] = useState<number>(0)
  const [bodyweightKg, setBodyweightKg] = useState<number>(0)
  const [targetDots, setTargetDots] = useState<number>(300)

  // Initialize from program maxes
  useMemo(() => {
    if (program?.meta) {
      setSquatKg(program.meta.target_squat_kg || 0)
      setBenchKg(program.meta.target_bench_kg || 0)
      setDeadliftKg(program.meta.target_dl_kg || 0)
      setBodyweightKg(program.meta.current_body_weight_kg || 0)
    }
  }, [program])

  // Calculate DOTS
  const result = useMemo(() => {
    if (!squatKg && !benchKg && !deadliftKg) return null
    return calculateDotsFromLifts(squatKg, benchKg, deadliftKg, bodyweightKg, sex)
  }, [squatKg, benchKg, deadliftKg, bodyweightKg, sex])

  // Get performance level
  const level = useMemo(() => {
    if (!result) return null
    return getDotsLevel(result.dots, sex)
  }, [result, sex])

  // Reverse calculation - total needed for target DOTS
  const totalNeeded = useMemo(() => {
    if (bodyweightKg <= 0) return null
    return totalForTargetDots(targetDots, bodyweightKg, sex)
  }, [targetDots, bodyweightKg, sex])

  // Weight class scenarios
  const weightClassScenarios = useMemo(() => {
    if (!result) return null
    const classes = [59, 66, 74, 83, 93, 105, 120, 130]
    return dotsAcrossWeightClasses(result.total_kg, classes, sex)
  }, [result, sex])

  return (
    <Stack gap="xl">
      <div>
        <Title order={2} mb="sm">DOTS Calculator</Title>
        <Text c="dimmed">
          Calculate your DOTS score based on your lifts and bodyweight
        </Text>
      </div>

      {/* Sex Toggle */}
      <SegmentedControl
        fullWidth
        data={[
          { label: 'Male', value: 'male' },
          { label: 'Female', value: 'female' },
        ]}
        value={sex}
        onChange={(val) => useSettingsStore.getState().setSex(val as Sex)}
      />

      {/* Input Grid */}
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md">
        <Stack gap="xs">
          <Text size="sm" fw={500}>Body Weight ({unit})</Text>
          <TextInput
            type="number"
            value={toDisplayUnit(bodyweightKg, unit) || ''}
            onChange={(e) => setBodyweightKg(Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0)}
          />
        </Stack>

        <Stack gap="xs">
          <Text size="sm" fw={500}>Squat ({unit})</Text>
          <TextInput
            type="number"
            value={toDisplayUnit(squatKg, unit) || ''}
            onChange={(e) => setSquatKg(Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0)}
          />
        </Stack>

        <Stack gap="xs">
          <Text size="sm" fw={500}>Bench ({unit})</Text>
          <TextInput
            type="number"
            value={toDisplayUnit(benchKg, unit) || ''}
            onChange={(e) => setBenchKg(Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0)}
          />
        </Stack>

        <Stack gap="xs">
          <Text size="sm" fw={500}>Deadlift ({unit})</Text>
          <TextInput
            type="number"
            value={toDisplayUnit(deadliftKg, unit) || ''}
            onChange={(e) => setDeadliftKg(Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0)}
          />
        </Stack>
      </SimpleGrid>

      {/* Result */}
      {result && (
        <Paper withBorder p="lg" radius="md">
          <Stack gap="xl">
            {/* Main Score */}
            <div style={{ textAlign: 'center' }}>
              <Text size="sm" c="dimmed">DOTS Score</Text>
              <Text fz={48} fw={700} c="blue">{result.dots}</Text>
            </div>

            {/* Stats Row */}
            <SimpleGrid cols={3} spacing="md" ta="center">
              <div>
                <Text size="sm" c="dimmed">Total</Text>
                <Text fz="xl" fw={700}>{displayWeight(result.total_kg, unit)}</Text>
              </div>
              <div>
                <Text size="sm" c="dimmed">Body Weight</Text>
                <Text fz="xl" fw={700}>{displayWeight(result.bodyweight_kg, unit)}</Text>
              </div>
              <div>
                <Text size="sm" c="dimmed">Level</Text>
                <Text
                  fz="xl"
                  fw={700}
                  c={
                    level?.name === 'World-class' ? 'blue' :
                    level?.name === 'Elite' ? 'blue' :
                    level?.name === 'Advanced' ? 'blue' : undefined
                  }
                >
                  {level?.name || 'N/A'}
                </Text>
              </div>
            </SimpleGrid>

            {/* Performance Context */}
            {level && (
              <Text size="sm" c="dimmed" ta="center">
                {level.context}
              </Text>
            )}
          </Stack>
        </Paper>
      )}

      {/* Reverse Calculator */}
      <Paper withBorder p="lg" radius="md">
        <Stack gap="md">
          <Text fw={500}>Target DOTS Calculator</Text>
          <Text size="sm" c="dimmed">
            What total do you need to hit a target DOTS score?
          </Text>

          <Group align="flex-end" gap="md">
            <Stack gap="xs">
              <Text size="sm" fw={500}>Target DOTS</Text>
              <TextInput
                type="number"
                value={targetDots || ''}
                onChange={(e) => setTargetDots(Number(e.currentTarget.value) || 0)}
              />
            </Stack>

            {totalNeeded && (
              <div style={{ textAlign: 'center', flex: 1 }}>
                <Text size="sm" c="dimmed">Required Total</Text>
                <Text fz="h3" fw={700} c="blue">
                  {displayWeight(totalNeeded, unit)}
                </Text>
              </div>
            )}
          </Group>
        </Stack>
      </Paper>

      {/* Weight Class Optimizer */}
      {weightClassScenarios && (
        <Paper withBorder p="lg" radius="md">
          <Stack gap="md">
            <Text fw={500}>DOTS at Different Body Weights</Text>
            <Text size="sm" c="dimmed">
              See how your DOTS changes across weight classes
            </Text>

            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Body Weight</Table.Th>
                  <Table.Th ta="right">DOTS</Table.Th>
                  <Table.Th ta="right">vs Current</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {weightClassScenarios.map((scenario) => (
                  <Table.Tr
                    key={scenario.bodyweightKg}
                    bg={scenario.bodyweightKg === bodyweightKg ? 'var(--mantine-color-blue-light)' : undefined}
                  >
                    <Table.Td>{scenario.bodyweightKg} kg</Table.Td>
                    <Table.Td ta="right" fw={500}>{scenario.dots}</Table.Td>
                    <Table.Td
                      ta="right"
                      c={
                        scenario.dots > (result?.dots || 0) ? 'blue' :
                        scenario.dots < (result?.dots || 0) ? 'red' : undefined
                      }
                    >
                      {scenario.dots > (result?.dots || 0) ? '+' : ''}
                      {(scenario.dots - (result?.dots || 0)).toFixed(1)}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
