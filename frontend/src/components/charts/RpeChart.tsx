import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts'
import { Paper, Text, Group, Box } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { formatDateShort } from '@/utils/dates'

function rpeColor(rpe: number | null): string {
  if (rpe === null) return '#6b7280'
  if (rpe <= 7) return '#22c55e'
  if (rpe === 8) return '#eab308'
  if (rpe === 9) return '#f97316'
  return '#ef4444'
}

function rpeLabel(rpe: number | null): string {
  if (rpe === null) return 'N/A'
  if (rpe <= 7) return 'Easy'
  if (rpe === 8) return 'Moderate'
  if (rpe === 9) return 'Hard'
  return 'Max Effort'
}

export default function RpeChart({ block }: { block?: string }) {
  const { program } = useProgramStore()

  const data = useMemo(() => {
    if (!program) return []

    return program.sessions
      .filter((s) => s.completed && s.session_rpe !== null && (s.block ?? 'current') === block)
      .map((session) => ({
        date: session.date,
        label: formatDateShort(session.date),
        rpe: session.session_rpe,
      }))
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-20)
  }, [program])

  if (!program || data.length === 0) {
    return (
      <Paper withBorder p="md" h="100%" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0 }}>
        <Text size="sm" c="dimmed">
          No sessions with RPE logged.
        </Text>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md">
      <Text size="sm" fw={500} mb="sm">Session RPE (Last {data.length})</Text>
      <div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} barCategoryGap={4}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" angle={-45} textAnchor="end" height={80} />
            <YAxis domain={[0, 10]} tickCount={10} />
            <Tooltip
              formatter={(value: number, name: string, props: any) => {
                const rpe = props.payload?.rpe
                return [`${value} - ${rpeLabel(rpe)}`]
              }}
              labelFormatter={(label: string) => `Session: ${label}`}
            />
            <Bar
              dataKey="rpe"
              radius={[4, 4, 0, 0]}
            >
              {data.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={rpeColor(entry.rpe)}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <Group gap="md" mt="sm" wrap="wrap" style={{ flexShrink: 0 }}>
        {[
          { color: '#22c55e', label: '\u22647 Easy' },
          { color: '#eab308', label: '8 Moderate' },
          { color: '#f97316', label: '9 Hard' },
          { color: '#ef4444', label: '10 Max' },
        ].map(({ color, label }) => (
          <Group key={label} gap="xs">
            <Box style={{ width: 12, height: 12, borderRadius: 2, backgroundColor: color }} />
            <Text size="xs" c="dimmed">{label}</Text>
          </Group>
        ))}
      </Group>
    </Paper>
  )
}
