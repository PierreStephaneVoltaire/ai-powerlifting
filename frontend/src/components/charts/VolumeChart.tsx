import { useMemo, useEffect, useState } from 'react'
import {
  BarChart,
  Bar,
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
import { weeklyVolumeByCategory6 } from '@/utils/volume'
import { displayWeight } from '@/utils/units'
import { fetchGlossary } from '@/api/client'
import type { GlossaryExercise } from '@powerlifting/types'

const CATEGORY_COLORS: Record<string, string> = {
  squat: '#ef4444',
  bench: '#3b82f6',
  deadlift: '#22c55e',
  back: '#f97316',
  chest: '#a855f7',
  arm: '#ec4899',
  legs: '#eab308',
  core: '#06b6d4',
  lower_back: '#14b8a6',
}

const CATEGORY_LABELS: Record<string, string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
  back: 'Back',
  chest: 'Chest',
  arm: 'Arms',
  legs: 'Legs',
  core: 'Core',
  lower_back: 'Lower Back',
}

const CATEGORIES = ['squat', 'bench', 'deadlift', 'back', 'chest', 'arm', 'legs', 'core', 'lower_back'] as const

export default function VolumeChart({ block }: { block?: string }) {
  const { program } = useProgramStore()
  const { unit } = useSettingsStore()
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])

  useEffect(() => {
    fetchGlossary().then(setGlossary).catch(() => {})
  }, [])

  const data = useMemo(() => {
    if (!program) return []
    return weeklyVolumeByCategory6(program.sessions, block, glossary)
  }, [program, block, glossary])

  if (!program || data.length === 0) {
    return (
      <Paper withBorder p="md" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0, flex: 1 }}>
        <Text size="sm" c="dimmed">No session data available</Text>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md">
      <Text fw={500} mb="sm">Weekly Volume by Category</Text>
      <div>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="week" tickFormatter={(v) => `W${v}`} />
            <YAxis
              tickFormatter={(value: number) => `${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(value: number) => [`${(value / 1000).toFixed(1)}k volume`]}
            />
            <Legend />
            {CATEGORIES.map((cat) => (
              <Bar
                key={cat}
                dataKey={cat}
                stackId="a"
                fill={CATEGORY_COLORS[cat]}
                name={CATEGORY_LABELS[cat]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Paper>
  )
}
