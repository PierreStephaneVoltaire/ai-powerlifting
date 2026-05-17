import { useEffect, useState } from 'react'
import { Plus, Edit2, Trash2 } from 'lucide-react'
import {
  Stack, Group, Title, Text, Paper, Badge, ActionIcon, SimpleGrid, Button, Box, Alert,
} from '@mantine/core'
import { fetchGlossary } from '../../api/client'
import { TemplateSessionModal } from './TemplateSessionModal'
import type { TemplateSession, GlossaryExercise } from '@powerlifting/types'

interface Props {
  sessions: TemplateSession[]
  onChange: (sessions: TemplateSession[]) => void
  disabled?: boolean
}

function blankSession(nextWeek: number): TemplateSession {
  return {
    id: crypto.randomUUID(),
    week_number: nextWeek,
    day_of_week: 'Monday',
    day_index: 0,
    label: '',
    exercises: [],
  }
}

export function TemplateSessionsEditor({ sessions, onChange, disabled }: Props) {
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const [glossaryError, setGlossaryError] = useState(false)
  const [editingSession, setEditingSession] = useState<TemplateSession | null>(null)

  useEffect(() => {
    fetchGlossary().then(setGlossary).catch(() => { setGlossary([]); setGlossaryError(true) })
  }, [])

  const weeks = Array.from(new Set(sessions.map(s => s.week_number))).sort((a, b) => a - b)

  function openNew() {
    const nextWeek = sessions.length ? Math.max(...sessions.map(s => s.week_number)) + 1 : 1
    setEditingSession(blankSession(nextWeek))
  }

  function openEdit(session: TemplateSession) {
    setEditingSession({ ...session, exercises: session.exercises.map(ex => ({ ...ex })) })
  }

  function handleSave(saved: TemplateSession) {
    const exists = sessions.some(s => s.id === saved.id)
    const updated = exists
      ? sessions.map(s => s.id === saved.id ? saved : s)
      : [...sessions, saved]
    onChange(updated)
    setEditingSession(null)
  }

  function handleDelete(id: string, label: string) {
    if (!confirm(`Delete session "${label || id}"?`)) return
    onChange(sessions.filter(s => s.id !== id))
  }

  return (
    <Stack gap="md">
      {glossaryError && (
        <Alert color="orange" title="Glossary unavailable">
          Exercise name autocomplete is unavailable. You can still type names manually.
        </Alert>
      )}
      <Group justify="flex-end">
        <Button size="sm" leftSection={<Plus size={16} />} onClick={openNew} disabled={disabled}>
          Add Session
        </Button>
      </Group>

      {weeks.length === 0 && (
        <Box ta="center" py={32}>
          <Text c="dimmed">No sessions defined. Click &quot;Add Session&quot; to get started.</Text>
        </Box>
      )}

      {weeks.map(week => {
        const weekSessions = sessions.filter(s => s.week_number === week)
        return (
          <Stack key={week} gap="sm">
            <Title order={4}>Week {week}</Title>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              {weekSessions.map(session => (
                <Paper key={session.id} withBorder p="md">
                  <Group justify="space-between" wrap="nowrap" mb={4}>
                    <Text fw={500} size="sm">Day {session.day_of_week}</Text>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon variant="subtle" size="sm" onClick={() => openEdit(session)} disabled={disabled}>
                        <Edit2 size={14} />
                      </ActionIcon>
                      <ActionIcon variant="subtle" color="red" size="sm" onClick={() => handleDelete(session.id, session.label)} disabled={disabled}>
                        <Trash2 size={14} />
                      </ActionIcon>
                    </Group>
                  </Group>
                  {session.label && <Badge size="sm" mb={4}>{session.label}</Badge>}
                  <Text size="xs" c="dimmed">{session.exercises.length} exercise{session.exercises.length !== 1 ? 's' : ''}</Text>
                </Paper>
              ))}
            </SimpleGrid>
          </Stack>
        )
      })}

      <TemplateSessionModal
        key={editingSession?.id ?? 'none'}
        session={editingSession}
        glossary={glossary}
        onSave={handleSave}
        onClose={() => setEditingSession(null)}
        disabled={disabled}
      />
    </Stack>
  )
}
