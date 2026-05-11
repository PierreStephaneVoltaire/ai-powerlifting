import React, { useEffect, useMemo, useState } from 'react'
import { Stack, Text, Table, Badge, Button, Group, Autocomplete } from '@mantine/core'
import type { ImportPending, GlossaryExercise } from '@powerlifting/types'
import { fetchGlossary } from '../../api/client'

interface Props {
  pendingImport: ImportPending | null
  overrides: Record<string, string>
  onOverride: (name: string, glossaryId: string) => void
  onNext: () => void
  onPrev: () => void
}

export const Step3_GlossaryReview: React.FC<Props> = ({
  pendingImport,
  overrides,
  onOverride,
  onNext,
  onPrev,
}) => {
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])

  useEffect(() => {
    fetchGlossary().then(setGlossary).catch(() => setGlossary([]))
  }, [])

  const glossaryByLabel = useMemo(() => {
    const map: Record<string, GlossaryExercise> = {}
    for (const g of glossary) map[g.name] = g
    return map
  }, [glossary])

  const autocompleteData = useMemo(() => Array.from(new Set(glossary.map((g) => g.name))), [glossary])

  if (!pendingImport) return null

  const sessions = pendingImport.ai_parse_result.sessions || []
  const exercises: any[] = []
  const seen = new Set<string>()

  sessions.forEach((s: any) => {
    s.exercises?.forEach((ex: any) => {
      if (!seen.has(ex.name)) {
        exercises.push(ex)
        seen.add(ex.name)
      }
    })
  })

  const confidenceBadge = (ex: any, overrideId?: string) => {
    if (overrideId) return <Badge color="violet" size="sm">manual override</Badge>
    if (ex.glossary_id && ex.fuzzy_match === false) return <Badge color="green" size="sm">exact</Badge>
    if (ex.glossary_id) return <Badge color="teal" size="sm">fuzzy</Badge>
    return <Badge color="red" size="sm">unresolved</Badge>
  }

  const handlePick = (originalName: string, pickedName: string) => {
    const match = glossaryByLabel[pickedName]
    if (match?.id) onOverride(originalName, match.id)
  }

  return (
    <Stack py="xl">
      <Text fw={500}>Exercise Resolution</Text>
      <Text size="sm" c="dimmed">
        Verify that the exercises from your file match correctly. Override any
        incorrect match by picking a different glossary entry.
      </Text>

      <Table withTableBorder withColumnBorders>
        <thead>
          <tr>
            <th>Name in File</th>
            <th>Matched Exercise</th>
            <th>Confidence</th>
            <th>Override</th>
          </tr>
        </thead>
        <tbody>
          {exercises.map((ex, idx) => {
            const overrideId = overrides[ex.name]
            const matchedLabel =
              (overrideId &&
                glossary.find((g) => g.id === overrideId)?.name) ||
              ex.glossary_id ||
              '—'
            return (
              <tr key={idx}>
                <td>{ex.name}</td>
                <td>{matchedLabel}</td>
                <td>{confidenceBadge(ex, overrideId)}</td>
                <td style={{ minWidth: 260 }}>
                  <Autocomplete
                    placeholder="Search glossary…"
                    data={autocompleteData}
                    limit={10}
                    onChange={(v) => handlePick(ex.name, v)}
                    size="xs"
                  />
                </td>
              </tr>
            )
          })}
        </tbody>
      </Table>

      <Group justify="space-between" mt="xl">
        <Button variant="outline" onClick={onPrev}>Back</Button>
        <Button onClick={onNext}>Continue</Button>
      </Group>
    </Stack>
  )
}
