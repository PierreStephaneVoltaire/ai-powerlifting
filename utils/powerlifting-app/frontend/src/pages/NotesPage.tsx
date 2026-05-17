import { useState, useEffect, useMemo } from 'react'
import { Save, BookOpen } from 'lucide-react'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import {
  Paper, Title, Text, Group, Stack, Button, Select, Textarea, Box,
} from '@mantine/core'
import type { BlockNote } from '@powerlifting/types'

export default function NotesPage() {
  const { readOnly } = useAuth()
  const { program, updateBlockNotes } = useProgramStore()
  const { pushToast } = useUiStore()
  const [selectedBlock, setSelectedBlock] = useState<string>('current')
  const [notes, setNotes] = useState<BlockNote[]>([])
  const [hasChanges, setHasChanges] = useState(false)

  const availableBlocks = useMemo(() => {
    if (!program) return ['current']
    const blocks = new Set<string>()
    for (const s of program.sessions) blocks.add(s.block ?? 'current')
    return Array.from(blocks).sort()
  }, [program])

  useEffect(() => {
    if (program?.meta?.block_notes) {
      setNotes(program.meta.block_notes)
    }
  }, [program])

  const currentNote = useMemo(
    () => notes.find((n) => n.block === selectedBlock),
    [notes, selectedBlock]
  )

  const noteText = currentNote?.notes ?? ''

  function handleNoteChange(value: string) {
    setNotes((prev) => {
      const idx = prev.findIndex((n) => n.block === selectedBlock)
      if (idx >= 0) {
        return prev.map((n, i) =>
          i === idx ? { ...n, notes: value, updated_at: new Date().toISOString() } : n
        )
      }
      return [...prev, { block: selectedBlock, notes: value, updated_at: new Date().toISOString() }]
    })
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      await updateBlockNotes(notes)
      setHasChanges(false)
      pushToast({ message: 'Notes saved', type: 'success' })
    } catch {
      pushToast({ message: 'Failed to save notes', type: 'error' })
    }
  }

  if (!program) return null

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Box>
          <Title order={2}>Notes</Title>
          <Text size="sm" c="dimmed">
            Block change log and comments — included in exports and analysis
          </Text>
        </Box>
        <Group gap="xs">
          {hasChanges && (
            <Button leftSection={<Save size={16} />}
            disabled={readOnly} onClick={handleSave}>
              Save
            </Button>
          )}
        </Group>
      </Group>

      {availableBlocks.length > 1 && (
        <Select
          label="Block"
          value={selectedBlock}
          onChange={(val) => val && setSelectedBlock(val)}
          data={availableBlocks.map((b) => ({
            value: b,
            label: b === 'current' ? 'Current' : b,
          }))}
          w={200}
        />
      )}

      <Paper withBorder p="md">
        <Stack gap="sm">
          <Group gap="xs">
            <BookOpen size={18} />
            <Text fw={600}>
              {selectedBlock === 'current' ? 'Current Block' : `Block: ${selectedBlock}`}
            </Text>
          </Group>
          <Text size="xs" c="dimmed">
            {currentNote?.updated_at
              ? `Last updated: ${new Date(currentNote.updated_at).toLocaleString()}`
              : 'No notes yet'}
          </Text>
          <Textarea
            placeholder="Enter block notes, changes, observations..."
            value={noteText}
            onChange={(e) => handleNoteChange(e.currentTarget.value)}
            minRows={8}
            autosize
            maxRows={20}
            disabled={readOnly}
          />
        </Stack>
      </Paper>

      {notes.filter((n) => n.notes.trim()).length > 0 && (
        <Stack gap="sm">
          <Text fw={600} size="sm">All block notes</Text>
          {notes
            .filter((n) => n.notes.trim())
            .sort((a, b) => a.block.localeCompare(b.block))
            .map((n) => (
              <Paper key={n.block} withBorder p="sm">
                <Group justify="space-between">
                  <Text fw={500} size="sm">
                    {n.block === 'current' ? 'Current' : n.block}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {new Date(n.updated_at).toLocaleDateString()}
                  </Text>
                </Group>
                <Text size="sm" mt={4} style={{ whiteSpace: 'pre-wrap' }}>
                  {n.notes}
                </Text>
              </Paper>
            ))}
        </Stack>
      )}
    </Stack>
  )
}
