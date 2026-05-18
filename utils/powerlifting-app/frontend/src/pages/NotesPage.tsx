import { useState, useEffect } from 'react'
import { Save, BookOpen, Plus, Trash2, Calendar, X } from 'lucide-react'
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

function formatDate(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return date
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function previewText(text: string): string {
  const trimmed = text.trim()
  if (!trimmed) return 'Empty note'
  return trimmed.length > 180 ? `${trimmed.slice(0, 177)}...` : trimmed
}

export default function NotesPage() {
  const { readOnly } = useAuth()
  const { program, updateBlockNotes } = useProgramStore()
  const { pushToast } = useUiStore()
  const [notes, setNotes] = useState<BlockNote[]>([])
  const [newDate, setNewDate] = useState(todayString())
  const [newText, setNewText] = useState('')
  const [editingDate, setEditingDate] = useState<string | null>(null)
  const [editDate, setEditDate] = useState('')
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (program) {
      setNotes(normalizeNotes(program.meta?.block_notes, program.meta?.program_start || todayString()))
      setEditingDate(null)
      setEditDate('')
      setEditText('')
    }
  }, [program])

  async function persistNotes(nextNotes: BlockNote[], successMessage: string) {
    setSaving(true)
    try {
      const sorted = sortNotes(nextNotes)
      await updateBlockNotes(sorted)
      setNotes(sorted)
      pushToast({ message: successMessage, type: 'success' })
    } catch {
      pushToast({ message: 'Failed to save notes', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  function startEdit(note: BlockNote) {
    if (readOnly) return
    setEditingDate(note.date)
    setEditDate(note.date)
    setEditText(note.notes)
  }

  function cancelEdit() {
    setEditingDate(null)
    setEditDate('')
    setEditText('')
  }

  async function addNote() {
    const text = newText.trim()
    if (!newDate || !text) return
    if (notes.some((note) => note.date === newDate)) {
      pushToast({ message: 'A note for this date already exists. Click that card to edit it.', type: 'error' })
      return
    }

    const now = new Date().toISOString()
    await persistNotes(
      [{ date: newDate, notes: text, updated_at: now }, ...notes],
      'Note added'
    )
    setNewText('')
    setNewDate(todayString())
  }

  async function saveEdit() {
    const originalDate = editingDate
    const text = editText.trim()
    if (!originalDate || !editDate || !text) return
    if (notes.some((note) => note.date === editDate && note.date !== originalDate)) {
      pushToast({ message: 'A note for this date already exists', type: 'error' })
      return
    }

    const now = new Date().toISOString()
    const nextNotes = notes.map((note) => (
      note.date === originalDate
        ? { ...note, date: editDate, notes: text, updated_at: now }
        : note
    ))
    await persistNotes(nextNotes, 'Note updated')
    cancelEdit()
  }

  async function removeNote(date: string) {
    if (!confirm('Delete this note?')) return
    await persistNotes(notes.filter((note) => note.date !== date), 'Note deleted')
    if (editingDate === date) cancelEdit()
  }

  if (!program) return null

  const canAdd = Boolean(newDate && newText.trim()) && !readOnly && !saving

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-start">
        <Box>
          <Title order={2}>Notes</Title>
          <Text size="sm" c="dimmed">
            Dated training context for exports and analysis
          </Text>
        </Box>
      </Group>

      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          <Group gap="xs">
            <Calendar size={16} style={{ opacity: 0.6 }} />
            <DatePickerInput
              value={newDate}
              valueFormat="YYYY-MM-DD"
              onChange={(date) => date && setNewDate(date)}
              size="xs"
              disabled={readOnly || saving}
              w={180}
              data-testid="notes-new-date"
            />
          </Group>
          <Textarea
            value={newText}
            onChange={(e) => setNewText(e.currentTarget.value)}
            autosize
            minRows={3}
            placeholder="Write a dated program note..."
            disabled={readOnly || saving}
            data-testid="notes-new-text"
          />
          <Group justify="flex-end">
            <Button
              leftSection={<Plus size={16} />}
              disabled={!canAdd}
              loading={saving}
              onClick={addNote}
              data-testid="notes-new-save"
            >
              Save Entry
            </Button>
          </Group>
        </Stack>
      </Paper>

      <Stack gap="md">
        {notes.map((note) => {
          const isEditing = editingDate === note.date

          if (isEditing) {
            return (
              <Paper key={note.date} withBorder p="md" radius="md" data-testid="program-note-card">
                <Stack gap="sm">
                  <Group justify="space-between" align="center">
                    <Group gap="xs">
                      <BookOpen size={18} />
                      <Text fw={600}>Edit Program Note</Text>
                    </Group>
                    <Group gap="xs">
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        onClick={cancelEdit}
                        disabled={saving}
                        aria-label="Cancel edit"
                        data-testid="program-note-edit-cancel"
                      >
                        <X size={16} />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => removeNote(note.date)}
                        disabled={saving || readOnly}
                        aria-label="Delete note"
                        data-testid="program-note-delete"
                      >
                        <Trash2 size={16} />
                      </ActionIcon>
                    </Group>
                  </Group>

                  <Group gap="xs" align="flex-end">
                    <Calendar size={16} style={{ opacity: 0.6, marginBottom: 8 }} />
                    <DatePickerInput
                      label="Date"
                      value={editDate}
                      valueFormat="YYYY-MM-DD"
                      onChange={(date) => date && setEditDate(date)}
                      size="xs"
                      disabled={saving || readOnly}
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
                    value={editText}
                    onChange={(e) => setEditText(e.currentTarget.value)}
                    autosize
                    minRows={4}
                    maxRows={18}
                    disabled={saving || readOnly}
                    data-testid="program-note-text"
                  />

                  <Group justify="flex-end">
                    <Button variant="subtle" onClick={cancelEdit} disabled={saving}>
                      Cancel
                    </Button>
                    <Button
                      leftSection={<Save size={16} />}
                      onClick={saveEdit}
                      disabled={saving || readOnly || !editDate || !editText.trim()}
                      loading={saving}
                      data-testid="program-note-edit-save"
                    >
                      Save
                    </Button>
                  </Group>
                </Stack>
              </Paper>
            )
          }

          return (
            <Paper
              key={note.date}
              withBorder
              p="md"
              radius="md"
              onClick={() => startEdit(note)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  startEdit(note)
                }
              }}
              role={readOnly ? undefined : 'button'}
              tabIndex={readOnly ? undefined : 0}
              style={{ cursor: readOnly ? 'default' : 'pointer' }}
              data-testid="program-note-card"
            >
              <Group justify="space-between" align="flex-start" gap="md">
                <Box style={{ flex: 1 }}>
                  <Group gap="xs" mb={6}>
                    <Calendar size={16} style={{ opacity: 0.6 }} />
                    <Text fw={700}>{formatDate(note.date)}</Text>
                    <Text size="xs" c="dimmed">{note.date}</Text>
                  </Group>
                  <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                    {previewText(note.notes)}
                  </Text>
                </Box>
                {!readOnly && (
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    disabled={saving}
                    onClick={(event) => {
                      event.stopPropagation()
                      removeNote(note.date)
                    }}
                    aria-label="Delete note"
                    data-testid="program-note-delete"
                  >
                    <Trash2 size={16} />
                  </ActionIcon>
                )}
              </Group>
            </Paper>
          )
        })}
      </Stack>

      {notes.length === 0 && (
        <Text ta="center" py={48} c="dimmed">
          No notes yet. Write a note above to add the first dated entry.
        </Text>
      )}
    </Stack>
  )
}
