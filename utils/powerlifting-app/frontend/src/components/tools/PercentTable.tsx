import { useMemo, useState } from 'react'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { displayWeight, toDisplayUnit, roundToNearest } from '@/utils/units'
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
} from '@mantine/core'
import { Edit3, Check } from 'lucide-react'

interface PercentRow {
  pct: number
  squat: number
  bench: number
  deadlift: number
  total: number
}

function buildPercentTable(squat: number, bench: number, deadlift: number): PercentRow[] {
  return Array.from({ length: 21 }, (_, i) => {
    const pct = 50 + i * 2.5
    return {
      pct,
      squat: roundToNearest(squat * pct / 100, 2.5),
      bench: roundToNearest(bench * pct / 100, 2.5),
      deadlift: roundToNearest(deadlift * pct / 100, 2.5),
      total: roundToNearest((squat + bench + deadlift) * pct / 100, 2.5),
    }
  })
}

export default function PercentTable() {
  const { program } = useProgramStore()
  const { unit } = useSettingsStore()
  const [isEditing, setIsEditing] = useState(false)
  const [editValues, setEditValues] = useState({
    squat: 0,
    bench: 0,
    deadlift: 0,
  })

  // Get current maxes from program
  const maxes = useMemo(() => {
    if (!program?.meta) return { squat: 0, bench: 0, deadlift: 0 }
    return {
      squat: program.meta.target_squat_kg || 0,
      bench: program.meta.target_bench_kg || 0,
      deadlift: program.meta.target_dl_kg || 0,
    }
  }, [program])

  // Initialize edit values when maxes change
  useMemo(() => {
    setEditValues(maxes)
  }, [maxes])

  // Build the table
  const table = useMemo(() => {
    return buildPercentTable(editValues.squat, editValues.bench, editValues.deadlift)
  }, [editValues])

  // Highlight percentages
  const highlightPcts = [65, 70, 75, 80, 85, 90, 95, 100]

  return (
    <Stack gap="xl">
      <div>
        <Title order={2} mb="xs">% of Max Table</Title>
        <Text c="dimmed">
          Calculate weights at different percentages of your maxes
        </Text>
      </div>

      {/* Max Inputs */}
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" align="center" mb="md">
          <Text fw={500}>Current Maxes ({unit})</Text>
          <Button
            size="xs"
            variant={isEditing ? 'filled' : 'default'}
            onClick={() => setIsEditing(!isEditing)}
            leftSection={isEditing ? <Check size={14} /> : <Edit3 size={14} />}
          >
            {isEditing ? 'Done' : 'Edit'}
          </Button>
        </Group>

        <SimpleGrid cols={3} spacing="md">
          <Stack gap={4}>
            <Text size="xs" c="dimmed">Squat</Text>
            {isEditing ? (
              <TextInput
                type="number"
                value={toDisplayUnit(editValues.squat, unit) || ''}
                onChange={(e) => setEditValues((v) => ({
                  ...v,
                  squat: Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0
                }))}
                size="md"
                style={{ fontWeight: 700 }}
              />
            ) : (
              <Text fz="lg" fw={700}>{displayWeight(maxes.squat, unit)}</Text>
            )}
          </Stack>
          <Stack gap={4}>
            <Text size="xs" c="dimmed">Bench</Text>
            {isEditing ? (
              <TextInput
                type="number"
                value={toDisplayUnit(editValues.bench, unit) || ''}
                onChange={(e) => setEditValues((v) => ({
                  ...v,
                  bench: Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0
                }))}
                size="md"
                style={{ fontWeight: 700 }}
              />
            ) : (
              <Text fz="lg" fw={700}>{displayWeight(maxes.bench, unit)}</Text>
            )}
          </Stack>
          <Stack gap={4}>
            <Text size="xs" c="dimmed">Deadlift</Text>
            {isEditing ? (
              <TextInput
                type="number"
                value={toDisplayUnit(editValues.deadlift, unit) || ''}
                onChange={(e) => setEditValues((v) => ({
                  ...v,
                  deadlift: Number(e.currentTarget.value) / (unit === 'lb' ? 2.20462 : 1) || 0
                }))}
                size="md"
                style={{ fontWeight: 700 }}
              />
            ) : (
              <Text fz="lg" fw={700}>{displayWeight(maxes.deadlift, unit)}</Text>
            )}
          </Stack>
        </SimpleGrid>

        {isEditing && (
          <Text size="xs" c="dimmed" mt="sm">
            Editing changes the table below. Save to program to persist.
          </Text>
        )}
      </Paper>

      {/* Percent Table */}
      <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
        <Table>
          <Table.Thead>
            <Table.Tr bg="var(--mantine-color-default)">
              <Table.Th>%</Table.Th>
              <Table.Th ta="right">Squat</Table.Th>
              <Table.Th ta="right">Bench</Table.Th>
              <Table.Th ta="right">Deadlift</Table.Th>
              <Table.Th ta="right">Total</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {table.map((row) => (
              <Table.Tr
                key={row.pct}
                bg={
                  row.pct === 100 ? 'var(--mantine-color-blue-light)' :
                  highlightPcts.includes(row.pct) ? 'var(--mantine-color-blue-light-hover)' :
                  undefined
                }
                fw={row.pct === 100 ? 700 : undefined}
              >
                <Table.Td
                  fw={highlightPcts.includes(row.pct) ? 500 : undefined}
                  c={highlightPcts.includes(row.pct) ? 'blue' : undefined}
                >
                  {row.pct}%
                </Table.Td>
                <Table.Td ta="right">{displayWeight(row.squat, unit)}</Table.Td>
                <Table.Td ta="right">{displayWeight(row.bench, unit)}</Table.Td>
                <Table.Td ta="right">{displayWeight(row.deadlift, unit)}</Table.Td>
                <Table.Td ta="right" fw={500}>{displayWeight(row.total, unit)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Quick Reference */}
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="sm">
        {[
          { label: 'Warmup', pct: 50 },
          { label: 'Working', pct: 70 },
          { label: 'Heavy', pct: 85 },
          { label: 'Max', pct: 100 },
        ].map(({ label, pct }) => {
          const row = table.find((r) => r.pct === pct)
          if (!row) return null
          return (
            <Paper key={pct} bg="var(--mantine-color-default)" p="sm" radius="md" ta="center">
              <Text size="xs" c="dimmed" mb={4}>{label} ({pct}%)</Text>
              <Text fw={700}>{displayWeight(row.total, unit)}</Text>
              <Text size="xs" c="dimmed">total</Text>
            </Paper>
          )
        })}
      </SimpleGrid>
    </Stack>
  )
}
