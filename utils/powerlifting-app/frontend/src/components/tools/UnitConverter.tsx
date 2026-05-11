import { useState, useMemo } from 'react'
import { kgToLb, lbToKg } from '@/utils/units'
import {
  Paper,
  Button,
  Group,
  Stack,
  SimpleGrid,
  TextInput,
  Text,
  Title,
  ActionIcon,
} from '@mantine/core'
import { ArrowLeftRight } from 'lucide-react'

type ConversionMode = 'kg-to-lb' | 'lb-to-kg'

export default function UnitConverter() {
  const [mode, setMode] = useState<ConversionMode>('kg-to-lb')
  const [inputValue, setInputValue] = useState('')

  const result = useMemo(() => {
    const value = parseFloat(inputValue)
    if (isNaN(value) || value <= 0) return null

    if (mode === 'kg-to-lb') {
      return {
        from: `${value} kg`,
        to: `${kgToLb(value)} lb`,
      }
    } else {
      return {
        from: `${value} lb`,
        to: `${lbToKg(value)} kg`,
      }
    }
  }, [inputValue, mode])

  const toggleMode = () => {
    setMode((prev) => (prev === 'kg-to-lb' ? 'lb-to-kg' : 'kg-to-lb'))
    setInputValue('')
  }

  const quickValues = useMemo(() => {
    if (mode === 'kg-to-lb') {
      return [20, 45, 60, 75, 90, 100, 120, 140, 160, 180, 200, 220, 250]
    }
    return [45, 100, 135, 185, 205, 225, 275, 315, 365, 405, 455, 495, 585]
  }, [mode])

  return (
    <Stack gap="xl">
      <div>
        <Title order={2} mb="xs">kg / lb Converter</Title>
        <Text c="dimmed">
          Convert between kilograms and pounds
        </Text>
      </div>

      {/* Mode Toggle */}
      <Paper withBorder p="md" radius="md">
        <Group justify="center" gap="md">
          <Button
            variant={mode === 'kg-to-lb' ? 'filled' : 'default'}
            onClick={() => setMode('kg-to-lb')}
          >
            kg &rarr; lb
          </Button>
          <ActionIcon
            variant="subtle"
            size="lg"
            onClick={toggleMode}
          >
            <ArrowLeftRight size={20} />
          </ActionIcon>
          <Button
            variant={mode === 'lb-to-kg' ? 'filled' : 'default'}
            onClick={() => setMode('lb-to-kg')}
          >
            lb &rarr; kg
          </Button>
        </Group>
      </Paper>

      {/* Input */}
      <Paper withBorder p="lg" radius="md">
        <Text size="sm" c="dimmed" mb="xs">
          Enter weight in {mode === 'kg-to-lb' ? 'kilograms' : 'pounds'}
        </Text>
        <Group gap="md" align="center">
          <TextInput
            type="number"
            flex={1}
            value={inputValue}
            onChange={(e) => setInputValue(e.currentTarget.value)}
            placeholder={mode === 'kg-to-lb' ? 'e.g., 100' : 'e.g., 225'}
            step={mode === 'kg-to-lb' ? 0.5 : 1}
            size="xl"
            style={{ textAlign: 'center', fontWeight: 700 }}
          />
          <Text size="lg" fw={500} c="dimmed">
            {mode === 'kg-to-lb' ? 'kg' : 'lb'}
          </Text>
        </Group>

        {/* Result */}
        {result && (
          <Paper bg="var(--mantine-color-blue-light)" p="md" radius="md" mt="md" ta="center">
            <Text size="sm" c="dimmed" mb={4}>
              {result.from} equals
            </Text>
            <Text fz="h2" fw={700} c="blue">
              {result.to}
            </Text>
          </Paper>
        )}
      </Paper>

      {/* Quick Reference */}
      <Paper withBorder p="md" radius="md">
        <Text fw={500} mb="sm">Quick Reference</Text>
        <SimpleGrid cols={{ base: 4, sm: 5, md: 7 }} spacing="xs">
          {quickValues.map((value) => (
            <Button
              key={value}
              variant="default"
              size="xs"
              onClick={() => setInputValue(String(value))}
            >
              {value} {mode === 'kg-to-lb' ? 'kg' : 'lb'}
            </Button>
          ))}
        </SimpleGrid>
      </Paper>

      {/* Conversion Table */}
      <Paper withBorder p="md" radius="md">
        <Text fw={500} mb="sm">Common Conversions</Text>
        <SimpleGrid cols={2} spacing="md">
          <Stack gap={4}>
            <Text fw={500} mb="xs">kg &rarr; lb</Text>
            <Text size="sm" c="dimmed">50 kg = 110.2 lb</Text>
            <Text size="sm" c="dimmed">75 kg = 165.3 lb</Text>
            <Text size="sm" c="dimmed">100 kg = 220.5 lb</Text>
            <Text size="sm" c="dimmed">125 kg = 275.6 lb</Text>
            <Text size="sm" c="dimmed">150 kg = 330.7 lb</Text>
            <Text size="sm" c="dimmed">200 kg = 440.9 lb</Text>
            <Text size="sm" c="dimmed">250 kg = 551.2 lb</Text>
          </Stack>
          <Stack gap={4}>
            <Text fw={500} mb="xs">lb &rarr; kg</Text>
            <Text size="sm" c="dimmed">135 lb = 61.2 kg</Text>
            <Text size="sm" c="dimmed">185 lb = 83.9 kg</Text>
            <Text size="sm" c="dimmed">225 lb = 102.1 kg</Text>
            <Text size="sm" c="dimmed">275 lb = 124.7 kg</Text>
            <Text size="sm" c="dimmed">315 lb = 142.9 kg</Text>
            <Text size="sm" c="dimmed">405 lb = 183.7 kg</Text>
            <Text size="sm" c="dimmed">495 lb = 224.5 kg</Text>
          </Stack>
        </SimpleGrid>
      </Paper>
    </Stack>
  )
}
