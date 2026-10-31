import { useEffect, useMemo, useState } from 'react'
import { Paper } from '@mantine/core'
import type { GlossaryExercise, MuscleGroup, Template } from '@powerlifting/types'
import { MuscleWorkloadMap } from '@/components/analysis/MuscleWorkloadMap'
import { sessionMuscleSets } from '@/utils/sessionWorkload'
import { fetchGlossary } from '@/api/client'

export function templateWeekCount(template: Template): number {
  const lastWeek = Math.max(0, ...template.sessions.map((session) => session.week_number || 0))
  return Math.max(1, lastWeek || template.meta.estimated_weeks || 1)
}

export function templateAvgWeeklyMuscleSets(template: Template, glossary: GlossaryExercise[]): Partial<Record<MuscleGroup, number>> {
  const entries = template.sessions.flatMap((session) =>
    session.exercises.map((exercise) => ({ name: exercise.name, sets: exercise.sets, reps: exercise.reps, kg: null }))
  )
  const totals = sessionMuscleSets(entries, glossary)
  const weeks = templateWeekCount(template)
  return Object.fromEntries(
    Object.entries(totals).map(([muscle, sets]) => [muscle, (sets ?? 0) / weeks])
  ) as Partial<Record<MuscleGroup, number>>
}

export function TemplateMuscleWorkload({ template }: { template: Template }) {
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])

  useEffect(() => {
    fetchGlossary().then(setGlossary).catch(console.error)
  }, [])

  const setsPerWeek = useMemo(() => templateAvgWeeklyMuscleSets(template, glossary), [template, glossary])
  const weeks = templateWeekCount(template)

  if (Object.keys(setsPerWeek).length === 0) return null

  return (
    <Paper withBorder p="md">
      <MuscleWorkloadMap
        setsPerWeek={setsPerWeek}
        analysisWeeks={weeks}
        subtitle={`Average weighted sets per week across the ${weeks}-week program`}
      />
    </Paper>
  )
}
