import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { Paper, Text } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { phaseColor } from '@/utils/phases'
import { displayWeight } from '@/utils/units'

export default function StrengthProgressChart({ block }: { block?: string }) {
  const { program } = useProgramStore()
  const { unit } = useSettingsStore()

  const data = useMemo(() => {
    if (!program) return []

    // Group sessions by week and find top sets
    const weekMap = new Map<number, { squat: number; bench: number; deadlift: number; phase: string }>()

    for (const session of program.sessions) {
      if (!session.completed || session.exercises.length === 0) continue
      if ((session.block ?? 'current') !== block) continue

      const week = session.week_number
      const current = weekMap.get(week) || { squat: 0, bench: 0, deadlift: 0, phase: session.phase.name }

      for (const ex of session.exercises) {
        if (ex.kg === null) continue
        const name = ex.name.toLowerCase()
        if (name.includes('squat')) {
          current.squat = Math.max(current.squat, ex.kg)
        } else if (name.includes('bench')) {
          current.bench = Math.max(current.bench, ex.kg)
        } else if (name.includes('deadlift') || name.includes('dl')) {
          current.deadlift = Math.max(current.deadlift, ex.kg)
        }
      }
      weekMap.set(week, current)
    }

    return Array.from(weekMap.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([week, data]) => ({
        week: `W${week}`,
        squat: data.squat,
        bench: data.bench,
        deadlift: data.deadlift,
        phase: data.phase,
      }))
  }, [program])

  const targetLines = useMemo(() => {
    if (!program?.meta) return null
    return {
      squat: program.meta.target_squat_kg,
      bench: program.meta.target_bench_kg,
      deadlift: program.meta.target_dl_kg,
    }
  }, [program])

  if (!program || data.length === 0) {
    return (
      <Paper withBorder p="md" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0, flex: 1 }}>
        <Text size="sm" c="dimmed">No completed sessions with lifts yet</Text>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md">
      <Text fw={500} mb="sm">Strength Progress</Text>
      <div>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="week" />
            <YAxis
              domain={[0, 'auto']}
              tickFormatter={(value: number) => displayWeight(value, unit)}
            />
            <Tooltip
              formatter={(value: number, name: string) => [`${name}: ${displayWeight(value, unit)}`]}
            />
            <Line
              type="monotone"
              dataKey="squat"
              stroke="#ef4444"
              strokeWidth={2}
              dot={{ fill: '#ef4444' }}
              name="Squat"
            />
            <Line
              type="monotone"
              dataKey="bench"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: '#3b82f6' }}
              name="Bench"
            />
            <Line
              type="monotone"
              dataKey="deadlift"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ fill: '#22c55e' }}
              name="Deadlift"
            />
            {targetLines && (
              <>
                <ReferenceLine
                  y={targetLines.squat}
                  stroke="#ef4444"
                  strokeDasharray="5 5"
                  label="Squat Target"
                />
                <ReferenceLine
                  y={targetLines.bench}
                  stroke="#3b82f6"
                  strokeDasharray="5 5"
                  label="Bench Target"
                />
                <ReferenceLine
                  y={targetLines.deadlift}
                  stroke="#22c55e"
                  strokeDasharray="5 5"
                  label="DL Target"
                />
              </>
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Paper>
  )
}
