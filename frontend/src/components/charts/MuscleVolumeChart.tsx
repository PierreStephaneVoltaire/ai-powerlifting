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
import { Paper, Text, Box } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { weeklyVolumeByMuscleGroup } from '@/utils/volume'
import { toDisplayUnit } from '@/utils/units'
import { fetchGlossary } from '@/api/client'
import type { GlossaryExercise } from '@powerlifting/types'

const CHART_COLORS = [
  '#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
  '#f43f5e', '#0ea5e9', '#10b981', '#f59e0b', '#d946ef',
  '#84cc16', '#06b6d4', '#8b5cf6', '#f97316', '#64748b'
]

export default function MuscleVolumeChart({ block }: { block?: string }) {
  const { program } = useProgramStore()
  const { unit } = useSettingsStore()
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 639px)').matches : false
  )

  useEffect(() => {
    const mql = window.matchMedia('(max-width: 639px)')
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    fetchGlossary().then(setGlossary).catch(() => {})
  }, [])

  const rawData = useMemo(() => {
    if (!program || !glossary.length) return []
    return weeklyVolumeByMuscleGroup(program.sessions, glossary, block)
  }, [program, block, glossary])

  const { chartData, muscleKeys } = useMemo(() => {
    if (!rawData.length) return { chartData: [], muscleKeys: [] }

    // 1. Identify all muscle groups present
    const allMuscles = new Set<string>()
    rawData.forEach(week => {
      Object.keys(week).forEach(k => {
        if (k !== 'week') allMuscles.add(k)
      })
    })

    const muscles = Array.from(allMuscles)

    if (!isMobile) {
      // PC: Show all non-zero
      const formatted = rawData.map(week => {
        const d: any = { week: week.week }
        muscles.forEach(m => {
          d[m] = toDisplayUnit(week[m] || 0, unit)
        })
        return d
      })
      return { chartData: formatted, muscleKeys: muscles.sort() }
    } else {
      // Mobile: Top 5 + Other
      // Calculate total volume per muscle to rank them
      const totals: Record<string, number> = {}
      muscles.forEach(m => {
        totals[m] = rawData.reduce((sum, week) => sum + (week[m] || 0), 0)
      })

      const sorted = muscles.sort((a, b) => totals[b] - totals[a])
      const top5 = sorted.slice(0, 5)
      const others = sorted.slice(5)

      const formatted = rawData.map(week => {
        const d: any = { week: week.week }
        top5.forEach(m => {
          d[m] = toDisplayUnit(week[m] || 0, unit)
        })
        if (others.length > 0) {
          const othersVol = others.reduce((sum, m) => sum + (week[m] || 0), 0)
          d['Other'] = toDisplayUnit(othersVol, unit)
        }
        return d
      })

      const keys = [...top5]
      if (others.length > 0) keys.push('Other')
      return { chartData: formatted, muscleKeys: keys }
    }
  }, [rawData, isMobile, unit])

  if (!program || rawData.length === 0) {
    return (
      <Paper withBorder p="md">
        <Text size="sm" c="dimmed" ta="center">No muscle volume data available</Text>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md">
      <Text fw={500} mb="sm">Weekly Volume by Muscle Group ({unit})</Text>
      <Box h={300}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="week" tickFormatter={(v) => `W${v}`} />
            <YAxis
              tickFormatter={(value: number) => {
                if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
                if (value >= 1000) return `${(value / 1000).toFixed(0)}k`
                return value.toString()
              }}
            />
            <Tooltip
              formatter={(value: number) => [
                `${Math.round(value).toLocaleString()} ${unit}`,
                ''
              ]}
              labelFormatter={(v) => `Week ${v}`}
            />
            <Legend iconType="circle" wrapperStyle={{ paddingTop: '10px' }} />
            {muscleKeys.map((muscle, i) => (
              <Bar
                key={muscle}
                dataKey={muscle}
                stackId="a"
                fill={muscle === 'Other' ? '#94a3b8' : CHART_COLORS[i % CHART_COLORS.length]}
                name={muscle.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                radius={0}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </Box>
    </Paper>
  )
}
