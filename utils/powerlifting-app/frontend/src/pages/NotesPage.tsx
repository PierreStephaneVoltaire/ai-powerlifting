import { useState, useEffect } from 'react'
import { Save, BookOpen, Plus, Trash2, Calendar } from 'lucide-react'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import {
  Paper, Title, Text, Group, Stack, Button, Textarea, Box, ActionIcon,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import type { BlockNote } from '@powerlifting/types'

function todayString(): string {
  return new Date().toISOString().split('T')[0]
}

function normalizeDate(note: Partial<BlockNote>, fallbackDate: string): string {
  const dated = typeof note.date === 'string' ? note.date.trim() : ''
  if (dated) return dated
  const updatedAt = typeof note.updated_at === 'string' ? note.updated_at.slice(0, 10) : ''
  return updatedAt || fallbackDate
}

function sortNotes(notes: BlockNote[]): BlockNote[] {
  return [...notes].sort((a, b) => b.date.localeCompare(a.date))
}

function nextAvailableDate(notes: BlockNote[]): string {
  const used = new Set(notes.map((note) => note.date))
  const cursor = new Date()
  for (let offset = 0; offset < 3650; offset += 1) {
    const candidate = cursor.toISOString().split('T')[0]
    if (!used.has(candidate)) return candidate
    cursor.setDate(cursor.getDate() - 1)
  }
  return todayString()
}

function normalizeNotes(rawNotes: BlockNote[] | undefined, fallbackDate: string): BlockNote[] {
  const byDate = new Map<string, BlockNote>()

  for (const raw of rawNotes ?? []) {
    const date = normalizeDate(raw, fallbackDate)
    const updatedAt = raw.updated_at || new Date().toISOString()
    const text = (raw.notes || '').trim()
    const legacyBlock = raw.block ? (raw.block === 'current' ? 'Current block' : `Block ${raw.block}`) : ''
    const notes = legacyBlock && !raw.date ? [`[${legacyBlock}]`, text].filter(Boolean).join('\n') : text
    const existing = byDate.get(date)

    if (!existing) {
      byDate.set(date, { ...raw, date, notes, updated_at: updatedAt })
      continue
    }

    byDate.set(date, {
      ...existing,
      notes: [existing.notes, notes].filter(Boolean).join('\n\n'),
      updated_at: existing.updated_at > updatedAt ? existing.updated_at : updatedAt,
    })
  }

  return sortNotes([...byDate.values()])
}

export default function NotesPage() {
  const { readOnly } = useAuth()
  const { program, updateBlockNotes } = useProgramStore()
  const { pushToast } = useUiStore()
  const [notes, setNotes] = useState<BlockNote[]>([])
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    if (program) {
      setNotes(normalizeNotes(program.meta?.block_notes, program.meta?.program_start || todayString()))
      setHasChanges(false)
    }
  }, [program])

  function updateNote(date: string, updates: Partial<BlockNote>) {
    const now = new Date().toISOString()
    setNotes((prev) => sortNotes(prev.map((note) => (
      note.date === date ? { ...note, ...updates, updated_at: now } : note
    ))))
    setHasChanges(true)
  }

  function addNote() {
    const date = nextAvailableDate(notes)
    setNotes((prev) => sortNotes([{ date, notes: '', updated_at: new Date().toISOString() }, ...prev]))
    setHasChanges(true)
  }

  function removeNote(date: string) {
    if (!confirm('Delete this note?')) return
    setNotes((prev) => prev.filter((note) => note.date !== date))
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      await updateBlockNotes(sortNotes(notes))
      setHasChanges(false)
      pushToast({ message: 'Notes saved', type: 'success' })
    } catch {
      pushToast({ message: 'Failed to save notes', type: 'error' })
    }
  }

  if (!program) return null

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-start">
        <Box>
          <Title order={2}>Notes</Title>
          <Text size="sm" c="dimmed">
            Dated training context for exports and analysis
          </Text>
        </Box>
        <Group gap="xs">
          {hasChanges && (
            <Button leftSection={<Save size={16} />} disabled={readOnly} onClick={handleSave} data-testid="notes-save">
              Save
            </Button>
          )}
          <Button variant="light" leftSection={<Plus size={16} />} disabled={readOnly} onClick={addNote} data-testid="notes-add-entry">
            Add Entry
          </Button>
        </Group>
      </Group>

      <Stack gap="md">
        {notes.map((note) => (
          <Paper key={note.date} withBorder p="md" data-testid="program-note-card">
            <Stack gap="sm">
              <Group justify="space-between" align="flex-start">
                <Group gap="xs">
                  <BookOpen size={18} />
                  <Text fw={600}>Program Note</Text>
                </Group>
                <ActionIcon
                  variant="subtle"
                  color="red"
                  disabled={readOnly}
                  onClick={() => removeNote(note.date)}
                  aria-label="Delete note"
                >
                  <Trash2 size={16} />
                </ActionIcon>
              </Group>

              <Group gap="xs" align="flex-end">
                <Calendar size={16} style={{ opacity: 0.6, marginBottom: 8 }} />
                <DatePickerInput
                  label="Date"
                  value={note.date}
                  valueFormat="YYYY-MM-DD"
                  onChange={(newDate) => {
                    if (!newDate) return
                    if (notes.some((existing) => existing.date === newDate && existing.date !== note.date)) {
                      pushToast({ message: 'A note for this date already exists', type: 'error' })
                      return
                    }
                    updateNote(note.date, { date: newDate })
                  }}
                  size="xs"
                  disabled={readOnly}
                  w={180}
                  data-testid="program-note-date"
                />
                {note.updated_at && (
                  <Text size="xs" c="dimmed" mb={6}>
                    Updated {new Date(note.updated_at).toLocaleString()}
                  </Text>
                )}
              </Group>

              <Textarea
                placeholder="Training observations, context changes, decisions, injuries, travel, recovery, or anything the analysis should weigh."
                value={note.notes}
                onChange={(e) => updateNote(note.date, { notes: e.currentTarget.value })}
                minRows={4}
                autosize
                maxRows={18}
                disabled={readOnly}
                data-testid="program-note-text"
              />
            </Stack>
          </Paper>
        ))}
      </Stack>

      {notes.length === 0 && (
        <Text ta="center" py={48} c="dimmed">
          No notes yet.
        </Text>
      )}
    </Stack>
  )
}
