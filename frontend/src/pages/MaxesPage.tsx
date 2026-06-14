import { useState, useMemo } from 'react'
import { PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { Paper, Title, Text, Select, SimpleGrid, Stack, Group, Table } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { allTimeMaxByExercise, maxByCategoryInWindow, categorizeExercise } from '@/utils/volume'
import { displayWeight } from '@/utils/units'
import type { LiftCategory } from '@/utils/volume'
import type { Session } from '@powerlifting/types'

const BIG3_COLORS: Record<string, string> = {
  squat: '#ef4444',
  bench: '#3b82f6',
  deadlift: '#22c55e',
}

const BIG3_LABELS: Record<string, string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
}

function big3PieData(maxes: Record<string, number>) {
  return (['squat', 'bench', 'deadlift'] as LiftCategory[])
    .filter((cat) => maxes[cat] > 0)
    .map((cat) => ({
      name: BIG3_LABELS[cat],
      value: maxes[cat],
      category: cat,
    }))
}

function Big3Pie({ maxes }: { maxes: Record<string, number> }) {
  const data = big3PieData(maxes)
  if (data.length === 0) return <Text size="sm" c="dimmed">No data.</Text>

  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={90}
          label={({ name, value }: { name: string; value: number }) => `${name}: ${value}kg`}
        >
          {data.map((entry) => (
            <Cell key={entry.category} fill={BIG3_COLORS[entry.category]} />
          ))}
        </Pie>
        <Tooltip formatter={(value: number) => [`${value} kg`]} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}

export default function MaxesPage() {
  const { program } = useProgramStore()
  const { unit } = useSettingsStore()
  const [block, setBlock] = useState('current')

  const availableBlocks = useMemo(() => {
    if (!program) return ['current']
    const blocks = new Set<string>()
    for (const s of program.sessions) blocks.add(s.block ?? 'current')
    return Array.from(blocks).sort()
  }, [program])

  const allTimeMaxes = useMemo(() => {
    if (!program) return new Map<string, { kg: number; displayName: string }>()
    return allTimeMaxByExercise(program.sessions, block)
  }, [program, block])

  const allTimeBig3 = useMemo(() => {
    const result: Record<string, number> = { squat: 0, bench: 0, deadlift: 0 }
    allTimeMaxes.forEach(({ kg }, key) => {
      const cat = categorizeExercise(key)
      if (cat in result && kg > result[cat]) result[cat] = kg
    })
    return result
  }, [allTimeMaxes])

  const maxTableRows = useMemo(() => {
    return Array.from(allTimeMaxes.entries())
      .sort((a, b) => b[1].kg - a[1].kg)
  }, [allTimeMaxes])

  const upcomingComps = useMemo(() => {
    if (!program?.competitions) return []
    return program.competitions
      .filter((c) => c.status !== 'skipped' && new Date(c.date) >= new Date())
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [program])

  const compWindows = useMemo(() => {
    if (!program || upcomingComps.length === 0) return []

    const allCompDates = [...upcomingComps.map((c) => c.date)].sort()
    const programStart = program.meta?.program_start ?? program.sessions[0]?.date ?? ''

    return upcomingComps.map((comp) => {
      const compIdx = allCompDates.indexOf(comp.date)
      const windowStart = compIdx > 0 ? allCompDates[compIdx - 1] : programStart
      const maxes = maxByCategoryInWindow(program.sessions, windowStart, comp.date, ['squat', 'bench', 'deadlift'], block)
      const targets = comp.targets
        ? { squat: comp.targets.squat_kg, bench: comp.targets.bench_kg, deadlift: comp.targets.deadlift_kg }
        : null
      return { comp, maxes, targets }
    })
  }, [program, upcomingComps, block])

  if (!program) {
    return <Text c="dimmed">Loading...</Text>
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <div>
          <Title order={2}>Maxes</Title>
          <Text size="sm" c="dimmed">
            Heaviest weight per exercise and big 3 strength distribution
          </Text>
        </div>
        {availableBlocks.length > 1 && (
          <Select
            value={block}
            onChange={(v) => setBlock(v ?? 'current')}
            data={availableBlocks.map((b) => ({
              value: b,
              label: b === 'current' ? 'Current Block' : b,
            }))}
            w={180}
          />
        )}
      </Group>

      {/* All-Time Max Table */}
      <Paper withBorder p="md">
        <Text fw={500} mb="xs">All-Time Maxes</Text>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Exercise</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>Max</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {maxTableRows.map(([, { kg, displayName }]) => (
              <Table.Tr key={displayName}>
                <Table.Td>{displayName}</Table.Td>
                <Table.Td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{displayWeight(kg, unit)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Big 3 Pie — All Time */}
      <Paper withBorder p="md">
        <Text fw={500} mb="xs">Big 3 Distribution (All Time)</Text>
        <Big3Pie maxes={allTimeBig3} />
      </Paper>

      {/* Per-Competition Goal Pies */}
      {compWindows.length > 0 && (
        <Stack gap="md">
          <Text fw={500}>Competition Goals</Text>
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
            {compWindows.map(({ comp, maxes, targets }) => (
              <Paper key={comp.date} withBorder p="md">
                <Stack gap="xs" mb="xs">
                  <Text fw={500}>{comp.name}</Text>
                  <Text size="sm" c="dimmed">
                    {comp.date} &middot; {comp.federation} &middot; {comp.weight_class_kg}kg
                  </Text>
                </Stack>
                <SimpleGrid cols={2} spacing="md">
                  <div>
                    <Text size="xs" c="dimmed" mb={4}>Current Max</Text>
                    <Big3Pie maxes={maxes} />
                  </div>
                  {targets && (
                    <div>
                      <Text size="xs" c="dimmed" mb={4}>Target</Text>
                      <Big3Pie maxes={targets} />
                    </div>
                  )}
                </SimpleGrid>
              </Paper>
            ))}
          </SimpleGrid>
        </Stack>
      )}
    </Stack>
  )
}
