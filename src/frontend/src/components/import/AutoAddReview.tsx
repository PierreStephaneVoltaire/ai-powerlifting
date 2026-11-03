import React from 'react'
import { Stack, Card, Text, TextInput, Select, Switch, Group, Button, Badge } from '@mantine/core'
import type { ExerciseCategory } from '@powerlifting/types'

export interface AutoAddDraft {
  name: string
  category: ExerciseCategory
  confirmed: boolean
}

interface Props {
  drafts: AutoAddDraft[]
  onChange: (drafts: AutoAddDraft[]) => void
  onNext: () => void
  onPrev: () => void
}

const CATEGORIES: ExerciseCategory[] = [
  'squat', 'bench', 'deadlift', 'back', 'chest', 'arm', 'legs', 'core', 'lower_back',
]

export const AutoAddReview: React.FC<Props> = ({ drafts, onChange, onNext, onPrev }) => {
  const update = (idx: number, patch: Partial<AutoAddDraft>) => {
    const next = drafts.slice()
    next[idx] = { ...next[idx], ...patch }
    onChange(next)
  }

  if (drafts.length === 0) {
    return (
      <Stack py="xl" align="center">
        <Text c="dimmed">No new glossary entries to review.</Text>
        <Group>
          <Button variant="outline" onClick={onPrev}>Back</Button>
          <Button onClick={onNext}>Continue</Button>
        </Group>
      </Stack>
    )
  }

  return (
    <Stack py="xl">
      <Text fw={500}>Proposed New Glossary Entries</Text>
      <Text size="sm" c="dimmed">
        These exercises were not found in your glossary. Edit each entry before
        it is added, or skip to exclude it.
      </Text>

      <Stack gap="sm">
        {drafts.map((d, idx) => (
          <Card key={idx} withBorder radius="md" padding="md">
            <Group justify="space-between" align="flex-start">
              <Stack gap="xs" style={{ flex: 1 }}>
                <Group>
                  <TextInput
                    label="Name"
                    value={d.name}
                    onChange={(e) => update(idx, { name: e.currentTarget.value })}
                    style={{ flex: 1 }}
                  />
                  <Select
                    label="Category"
                    data={CATEGORIES}
                    value={d.category}
                    onChange={(v) => v && update(idx, { category: v as ExerciseCategory })}
                  />
                </Group>
                <Badge color="yellow" size="sm">fatigue_profile: pending</Badge>
              </Stack>
              <Switch
                label={d.confirmed ? 'Add' : 'Skip'}
                checked={d.confirmed}
                onChange={(e) => update(idx, { confirmed: e.currentTarget.checked })}
                mt="xl"
              />
            </Group>
          </Card>
        ))}
      </Stack>

      <Group justify="space-between" mt="xl">
        <Button variant="outline" onClick={onPrev}>Back</Button>
        <Button onClick={onNext}>Continue</Button>
      </Group>
    </Stack>
  )
}
