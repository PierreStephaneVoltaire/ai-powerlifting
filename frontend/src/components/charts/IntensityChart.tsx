import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts'
import { Paper, Text } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'

export default function IntensityChart({ block }: { block?: string }) {
  const { program } = useProgramStore()
  const { unit } = useSettingsStore()

  const data = useMemo(() => {
    if (!program?.meta) return []

    const targets = {
      squat: program.meta.target_squat_kg || 0,
      bench: program.meta.target_bench_kg || 0,
      deadlift: program.meta.target_dl_kg || 0,
    }

    return program.sessions
      .filter((s) => s.completed && (s.block ?? 'current') === block)
      .map((session) => {
        let squatPct = 0
        let benchPct = 0
        let dlPct = 0

        for (const ex of session.exercises) {
          if (!ex.kg) continue
          const name = ex.name.toLowerCase()

          if (name.includes('squat') && targets.squat > 0) {
            squatPct = Math.max(squatPct, (ex.kg / targets.squat) * 100)
          } else if (name.includes('bench') && targets.bench > 0) {
            benchPct = Math.max(benchPct, (ex.kg / targets.bench) * 100)
          } else if ((name.includes('deadlift') || name.includes('dl')) && targets.deadlift > 0) {
            dlPct = Math.max(dlPct, (ex.kg / targets.deadlift) * 100)
          }
        }

        return {
          date: session.date,
          squat: squatPct,
          bench: benchPct,
          deadlift: dlPct,
        }
      })
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [program])

  if (!program || data.length === 0) {
    return (
      <Paper withBorder p="md" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0, flex: 1 }}>
        <Text size="sm" c="dimmed">No completed sessions with weights logged.</Text>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md">
      <Text fw={500} mb="sm">Intensity (% of Target Max)</Text>
      <div>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" />
            <YAxis domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
            <Tooltip
              formatter={(value: number) => [`${value.toFixed(1)}%`]}
              labelFormatter={(label: string) => `Date: ${label}`}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="squat"
              stroke="#ef4444"
              strokeWidth={2}
              dot={{ r: 3 }}
              name="Squat"
            />
            <Line
              type="monotone"
              dataKey="bench"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ r: 3 }}
              name="Bench"
            />
            <Line
              type="monotone"
              dataKey="deadlift"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ r: 3 }}
              name="Deadlift"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Paper>
  )
}
