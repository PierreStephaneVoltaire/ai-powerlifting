import { useState } from 'react'
import { ActionIcon, Button, Group, Paper, Stack, Text, TextInput } from '@mantine/core'
import { X } from 'lucide-react'
import { normalizePlateInventory } from '@/utils/plateInventory'

interface PlateInventoryEditorProps {
  unit: 'kg' | 'lb'
  plates: number[]
  onChange: (plates: number[]) => void
  compact?: boolean
}

export default function PlateInventoryEditor({
  unit,
  plates,
  onChange,
  compact = false,
}: PlateInventoryEditorProps) {
  const [draftPlate, setDraftPlate] = useState('')

  const handleAdd = () => {
    const parsed = Number.parseFloat(draftPlate.replace(',', '.').trim())
    if (!Number.isFinite(parsed) || parsed <= 0) return
    onChange(normalizePlateInventory([...plates, parsed]))
    setDraftPlate('')
  }

  const handleRemove = (plate: number) => {
    onChange(normalizePlateInventory(plates.filter((value) => value !== plate)))
  }

  return (
    <Stack gap={compact ? 4 : 8}>
      <Group justify="space-between" align="center" wrap="nowrap">
        <Text size={compact ? 'xs' : 'sm'} fw={500}>
          Plate Inventory
        </Text>
        <Text size="xs" c="dimmed">
          Values only, no counts
        </Text>
      </Group>

      {plates.length > 0 ? (
        <Group gap={6} wrap="wrap">
          {plates.map((plate) => (
            <Paper key={plate} withBorder radius="xl" px={8} py={4}>
              <Group gap={4} wrap="nowrap">
                <Text size="xs" fw={600}>
                  {plate}
                  <Text span size="xs" c="dimmed" ml={2}>
                    {unit}
                  </Text>
                </Text>
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="red"
                  onClick={() => handleRemove(plate)}
                  aria-label={`Remove ${plate}${unit} plate`}
                >
                  <X size={12} />
                </ActionIcon>
              </Group>
            </Paper>
          ))}
        </Group>
      ) : (
        <Text size="xs" c="dimmed">
          Using built-in default {unit.toUpperCase()} plates
        </Text>
      )}

      <Group gap="xs" wrap="nowrap" align="flex-end">
        <TextInput
          value={draftPlate}
          onChange={(event) => setDraftPlate(event.currentTarget.value)}
          inputMode="decimal"
          placeholder={`Add ${unit} plate`}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              handleAdd()
            }
          }}
          style={{ flex: 1 }}
        />
        <Button variant="default" onClick={handleAdd} size="sm">
          Add
        </Button>
      </Group>
    </Stack>
  )
}
