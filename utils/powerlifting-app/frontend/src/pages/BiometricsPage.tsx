import { useState, useEffect } from 'react'
import { Plus, Trash2, Save, Calendar, Droplets, Flame, CheckCircle, XCircle, Moon, Beef } from 'lucide-react'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import {
  Paper, Title, Text, Group, Stack, SimpleGrid, Button, ActionIcon,
  TextInput, Textarea, Select, SegmentedControl, Box,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import type { DietNote } from '@powerlifting/types'

function parseDateString(ds: string): Date | null {
  if (!ds) return null
  const parts = ds.split('-')
  if (parts.length !== 3) return null
  return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
}

function toDateString(d: Date): string {
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

export default function BiometricsPage() {
  const { program, updateDietNotes } = useProgramStore()
  const { pushToast } = useUiStore()
  const [notes, setNotes] = useState<DietNote[]>([])
  const [hasChanges, setHasChanges] = useState(false)
  const [editingDate, setEditingDate] = useState<string | null>(null)

  useEffect(() => {
    if (program?.diet_notes) {
      const sorted = [...program.diet_notes].sort((a, b) => b.date.localeCompare(a.date))
      setNotes(sorted)
    }
  }, [program])

  function updateNote(date: string, updates: Partial<DietNote>) {
    setNotes((prev) =>
      prev.map((n) => (n.date === date ? { ...n, ...updates } : n))
    )
    setHasChanges(true)
  }

  function addNote() {
    const today = new Date().toISOString().split('T')[0]
    if (notes.some((n) => n.date === today)) {
      pushToast({ message: 'An entry for today already exists', type: 'error' })
      return
    }
    setNotes((prev) => [{ date: today, notes: '' }, ...prev])
    setHasChanges(true)
    setEditingDate(today)
  }

  function removeNote(date: string) {
    if (!confirm('Delete this entry?')) return
    setNotes((prev) => prev.filter((n) => n.date !== date))
    setHasChanges(true)
  }

  async function handleSave() {
    try {
      const sorted = [...notes].sort((a, b) => b.date.localeCompare(a.date))
      await updateDietNotes(sorted)
      setHasChanges(false)
      pushToast({ message: 'Biometrics saved', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to save biometrics', type: 'error' })
    }
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Box>
          <Title order={2}>Biometrics</Title>
          <Text size="sm" c="dimmed">
            Track daily nutrition, sleep, and recovery metrics
          </Text>
        </Box>
        <Group gap="xs">
          {hasChanges && (
            <Button leftSection={<Save size={16} />} onClick={handleSave}>
              Save
            </Button>
          )}
          <Button variant="light" leftSection={<Plus size={16} />} onClick={addNote}>
            Add Entry
          </Button>
        </Group>
      </Group>

      <Stack gap="md">
        {notes.map((note) => (
          <Paper key={note.date} withBorder p="md">
            <Stack gap="sm">
              {/* Date Header */}
              <Group justify="space-between">
                <Group gap="xs">
                  <Calendar size={16} style={{ opacity: 0.6 }} />
                  <DatePickerInput
                    value={note.date}
                    valueFormat="YYYY-MM-DD"
                    onChange={(d) => {
                      if (d) {
                        const newDate = d
                        if (notes.some((n) => n.date === newDate && n.date !== note.date)) {
                          pushToast({ message: 'An entry for this date already exists', type: 'error' })
                          return
                        }
                        updateNote(note.date, { date: newDate })
                      }
                    }}
                    size="xs"
                    style={{ width: 'auto' }}
                  />
                </Group>
                <ActionIcon
                  variant="subtle"
                  color="red"
                  onClick={() => removeNote(note.date)}
                >
                  <Trash2 size={16} />
                </ActionIcon>
              </Group>

              {/* Row 1: Calories + Macros */}
              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                <Box>
                  <Text size="xs" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                    <Flame size={12} />
                    Avg Daily Calories
                  </Text>
                  <TextInput
                    type="number"
                    value={note.avg_daily_calories ?? ''}
                    onChange={(e) => updateNote(note.date, {
                      avg_daily_calories: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value),
                    })}
                    placeholder="e.g. 2500"
                    size="xs"
                  />
                </Box>

                <Box>
                  <Text size="xs" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                    <Beef size={12} />
                    Avg Protein (g)
                  </Text>
                  <TextInput
                    type="number"
                    value={note.avg_protein_g ?? ''}
                    onChange={(e) => updateNote(note.date, {
                      avg_protein_g: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value),
                    })}
                    placeholder="e.g. 180"
                    size="xs"
                  />
                </Box>

                <Box>
                  <Text size="xs" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                    <Text component="span" size="xs" fw={700} c="dimmed">C</Text>
                    Avg Carbs (g)
                  </Text>
                  <TextInput
                    type="number"
                    value={note.avg_carb_g ?? ''}
                    onChange={(e) => updateNote(note.date, {
                      avg_carb_g: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value),
                    })}
                    placeholder="e.g. 250"
                    size="xs"
                  />
                </Box>

                <Box>
                  <Text size="xs" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                    <Text component="span" size="xs" fw={700} c="dimmed">F</Text>
                    Avg Fat (g)
                  </Text>
                  <TextInput
                    type="number"
                    value={note.avg_fat_g ?? ''}
                    onChange={(e) => updateNote(note.date, {
                      avg_fat_g: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value),
                    })}
                    placeholder="e.g. 80"
                    size="xs"
                  />
                </Box>
              </SimpleGrid>

              {/* Row 2: Sleep + Water + Consistency */}
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                <Box>
                  <Text size="xs" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                    <Moon size={12} />
                    Avg Sleep (hrs/night)
                  </Text>
                  <TextInput
                    type="number"
                    value={note.avg_sleep_hours ?? ''}
                    onChange={(e) => updateNote(note.date, {
                      avg_sleep_hours: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value),
                    })}
                    placeholder="e.g. 7.5"
                    step={0.5}
                    size="xs"
                  />
                </Box>

                <Box>
                  <Text size="xs" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                    <Droplets size={12} />
                    Water Intake
                  </Text>
                  <Group gap="xs" wrap="nowrap">
                    <TextInput
                      type="number"
                      value={note.water_intake ?? ''}
                      onChange={(e) => updateNote(note.date, {
                        water_intake: e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value),
                      })}
                      placeholder="e.g. 2.5"
                      step={0.1}
                      style={{ flex: 1 }}
                      size="xs"
                    />
                    <Select
                      value={note.water_unit || 'litres'}
                      onChange={(v) => updateNote(note.date, {
                        water_unit: (v || 'litres') as 'litres' | 'cups',
                      })}
                      data={[
                        { value: 'litres', label: 'L' },
                        { value: 'cups', label: 'cups' },
                      ]}
                      size="xs"
                      style={{ width: 80 }}
                    />
                  </Group>
                </Box>

                <Box>
                  <Text size="xs" c="dimmed" style={{ marginBottom: 4 }}>Nutrition Consistency</Text>
                  <SegmentedControl
                    fullWidth
                    size="xs"
                    value={
                      note.consistent === true ? 'consistent'
                      : note.consistent === false ? 'on_off'
                      : ''
                    }
                    onChange={(v) => {
                      if (v === 'consistent') updateNote(note.date, { consistent: true })
                      else if (v === 'on_off') updateNote(note.date, { consistent: false })
                    }}
                    data={[
                      {
                        value: 'consistent',
                        label: (
                          <Group gap={4} wrap="nowrap">
                            <CheckCircle size={12} />
                            <Text size="xs">Consistent</Text>
                          </Group>
                        ),
                      },
                      {
                        value: 'on_off',
                        label: (
                          <Group gap={4} wrap="nowrap">
                            <XCircle size={12} />
                            <Text size="xs">On & Off</Text>
                          </Group>
                        ),
                      },
                    ]}
                  />
                </Box>
              </SimpleGrid>

              {/* Notes Textarea */}
              <Textarea
                value={note.notes}
                onChange={(e) => updateNote(note.date, { notes: e.currentTarget.value })}
                autosize
                minRows={2}
                placeholder="Notes, observations, how you felt..."
                size="xs"
              />
            </Stack>
          </Paper>
        ))}
      </Stack>

      {notes.length === 0 && (
        <Text ta="center" py={48} c="dimmed">
          No biometrics entries yet. Click &quot;Add Entry&quot; to get started.
        </Text>
      )}
    </Stack>
  )
}
