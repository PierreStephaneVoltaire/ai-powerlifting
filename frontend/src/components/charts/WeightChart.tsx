import { useMemo, useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts'
import { Paper, Text } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { mergeBodyweightEntries } from '@/utils/bodyweight'
import { displayWeight } from '@/utils/units'
import * as api from '@/api/client'
import type { WeightEntry } from '@powerlifting/types'

export default function WeightChart() {
  const { program, version } = useProgramStore()
  const { unit } = useSettingsStore()
  const [entries, setEntries] = useState<WeightEntry[]>([])

  useEffect(() => {
    async function loadEntries() {
      try {
        const log = await api.fetchWeightLog(version)
        setEntries(log || [])
      } catch (err) {
        console.error('Failed to load weight log:', err)
      }
    }
    loadEntries()
  }, [version])

  const data = useMemo(() => {
    const merged = mergeBodyweightEntries(entries, program?.sessions ?? [])
    if (merged.length === 0) return []

    return merged
      .map((entry) => ({
        date: entry.date,
        kg: entry.kg,
        lb: entry.kg * 2.20462,
      }))
  }, [entries, program?.sessions])

  const weightClassCeiling = program?.meta?.weight_class_kg

  if (data.length === 0) {
    return (
      <Paper withBorder p="md" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0, flex: 1 }}>
        <Text size="sm" c="dimmed">
          No weight entries logged. Use the Weight Tracker to add entries.
        </Text>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md">
      <Text fw={500} mb="sm">Body Weight Trend</Text>
      <div>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(value: number) => `${value.toFixed(1)} kg`}
            />
            <Tooltip
              formatter={(value: number, name: string) => [`${value.toFixed(1)} ${name}`]}
              labelFormatter={(label: string) => `Date: ${label}`}
            />
            <Line
              type="monotone"
              dataKey="kg"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: '#3b82f6' }}
              name="kg"
            />
            {weightClassCeiling && (
              <ReferenceLine
                y={weightClassCeiling}
                stroke="#ef4444"
                strokeDasharray="5 5"
                label={`${weightClassCeiling}kg Class`}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {weightClassCeiling && data && data.length > 0 && (
        <Text size="xs" c="dimmed" mt="xs" style={{ flexShrink: 0 }}>
          Current: {displayWeight(data[data.length - 1].kg, unit)} &bull; Target: {weightClassCeiling}kg class
        </Text>
      )}
    </Paper>
  )
}
