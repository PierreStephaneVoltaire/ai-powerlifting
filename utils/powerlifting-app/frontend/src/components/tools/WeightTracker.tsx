import { useState, useMemo, useEffect } from 'react'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { displayWeight, toDisplayUnit, fromDisplayUnit, kgToLb } from '@/utils/units'
import { daysUntil, formatDateShort } from '@/utils/dates'
import { format, parse, subDays } from 'date-fns'
import {
  Paper,
  Button,
  Group,
  Stack,
  SimpleGrid,
  TextInput,
  ActionIcon,
  Progress,
  Text,
  Title,
  Loader,
} from '@mantine/core'
import { Plus, Trash2, TrendingDown, TrendingUp } from 'lucide-react'
import type { WeightEntry } from '@powerlifting/types'
import * as api from '@/api/client'

export default function WeightTracker() {
  const { program, version, addWeightEntry, removeWeightEntry } = useProgramStore()
  const { unit } = useSettingsStore()
  const { pushToast } = useUiStore()

  const [entries, setEntries] = useState<WeightEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [newDate, setNewDate] = useState(new Date().toISOString().split('T')[0])
  const [newWeight, setNewWeight] = useState('')

  // Load weight log
  useEffect(() => {
    async function loadEntries() {
      try {
        const log = await api.fetchWeightLog(version)
        setEntries(log || [])
      } catch (err) {
        console.error('Failed to load weight log:', err)
      } finally {
        setIsLoading(false)
      }
    }
    loadEntries()
  }, [version])

  // Get current body weight and target
  const meta = program?.meta
  const sortedEntries = useMemo(
    () => [...entries].sort((a, b) => b.date.localeCompare(a.date)),
    [entries],
  )

  const currentBW = sortedEntries[0]?.kg || meta?.current_body_weight_kg || 0
  const targetClass = meta?.weight_class_kg || 74

  const confirmBy = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    const nextCompetition = [...(program?.competitions ?? [])]
      .filter((comp) => comp.status !== 'skipped' && comp.status !== 'completed' && comp.date >= today)
      .sort((a, b) => a.date.localeCompare(b.date))[0]

    if (!nextCompetition?.date) return null

    return format(
      subDays(parse(nextCompetition.date, 'yyyy-MM-dd', new Date()), 30),
      'yyyy-MM-dd',
    )
  }, [program?.competitions])

  // Calculate weight delta
  const weightDelta = useMemo(() => {
    if (!targetClass || !currentBW) return null
    return {
      kg: parseFloat((currentBW - targetClass).toFixed(2)),
      lb: parseFloat((kgToLb(currentBW - targetClass)).toFixed(1)),
      over: currentBW > targetClass,
    }
  }, [currentBW, targetClass])

  // Calculate rate of change (kg/week)
  const rateOfChange = useMemo(() => {
    if (sortedEntries.length < 2) return null
    const newest = sortedEntries[0]
    const oldest = sortedEntries[sortedEntries.length - 1]
    const daysDiff = Math.abs(new Date(newest.date).getTime() - new Date(oldest.date).getTime()) / (1000 * 60 * 60 * 24)
    if (daysDiff === 0) return null
    const kgDiff = newest.kg - oldest.kg
    return {
      kgPerWeek: parseFloat(((kgDiff / daysDiff) * 7).toFixed(2)),
      losing: kgDiff < 0,
    }
  }, [sortedEntries])

  // Peak week estimate
  const peakWeekWeight = useMemo(() => {
    if (!currentBW) return null
    return parseFloat((currentBW * 0.975).toFixed(1))
  }, [currentBW])

  // Days until confirmation
  const daysToConfirm = useMemo(() => {
    if (!confirmBy) return null
    return daysUntil(confirmBy)
  }, [confirmBy])

  // Add entry handler
  const handleAddEntry = async () => {
    if (!newWeight || !newDate) return

    const kg = fromDisplayUnit(Number(newWeight), unit)
    try {
      await api.addWeightEntry(version, { date: newDate, kg })
      setEntries((prev) => {
        const withoutDate = prev.filter((entry) => entry.date !== newDate)
        return [...withoutDate, { date: newDate, kg }].sort((a, b) => b.date.localeCompare(a.date))
      })
      setNewWeight('')
      pushToast({ message: 'Weight entry saved', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to add entry', type: 'error' })
    }
  }

  // Delete entry handler
  const handleDeleteEntry = async (date: string) => {
    try {
      await api.removeWeightEntry(version, date)
      setEntries((prev) => prev.filter((e) => e.date !== date))
      pushToast({ message: 'Entry removed', type: 'success' })
    } catch (err) {
      pushToast({ message: 'Failed to remove entry', type: 'error' })
    }
  }

  // Progress percentage
  const progressPct = useMemo(() => {
    if (!currentBW || !targetClass) return 0
    // If over target, show how far over
    if (currentBW > targetClass) {
      return Math.min(100, ((currentBW - targetClass) / targetClass) * 100)
    }
    // If under target, show how close to ceiling
    return Math.min(100, (currentBW / targetClass) * 100)
  }, [currentBW, targetClass])

  if (isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader size="sm" />
      </Group>
    )
  }

  return (
    <Stack gap="xl">
      <div>
        <Title order={2} mb="xs">Weight Tracker</Title>
        <Text c="dimmed">
          Track body weight progress toward your weight class
        </Text>
      </div>

      {/* Progress Card */}
      <Paper withBorder p="lg" radius="md">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text size="sm" c="dimmed">Current Weight</Text>
              <Text fz="h1" fw={700}>{displayWeight(currentBW, unit)}</Text>
            </div>
            <div style={{ textAlign: 'right' }}>
              <Text size="sm" c="dimmed">Target Class</Text>
              <Text fz="h1" fw={700}>{targetClass} kg</Text>
            </div>
          </Group>

          {/* Progress Bar */}
          <Stack gap={4}>
            <Progress
              value={Math.min(100, progressPct)}
              color={currentBW <= targetClass ? 'blue' : 'red'}
              size="lg"
              radius="xl"
            />
            <Group justify="space-between">
              <Text size="xs" c="dimmed">0</Text>
              <Text size="xs" c="dimmed">{displayWeight(targetClass, unit)}</Text>
              <Text size="xs" c="dimmed">{displayWeight(targetClass * 1.1, unit)}</Text>
            </Group>
          </Stack>

          {/* Delta */}
          {weightDelta && (
            <Paper
              bg={weightDelta.over ? 'var(--mantine-color-red-light)' : 'var(--mantine-color-blue-light)'}
              p="sm"
              radius="md"
            >
              <Group gap="xs">
                {weightDelta.over ? (
                  <TrendingUp size={20} />
                ) : (
                  <TrendingDown size={20} />
                )}
                <Text fw={500}>
                  {weightDelta.over ? '+' : ''}{displayWeight(Math.abs(weightDelta.kg), unit)} {weightDelta.over ? 'over' : 'under'}
                </Text>
              </Group>
            </Paper>
          )}

          {/* Stats Row */}
          <SimpleGrid cols={3} spacing="md" ta="center" style={{ borderTop: '1px solid var(--mantine-color-default-border)', paddingTop: 'var(--mantine-spacing-md)' }}>
            <div>
              <Text size="xs" c="dimmed">Rate</Text>
              <Text
                fw={700}
                c={rateOfChange?.losing ? 'blue' : 'red'}
              >
                {rateOfChange ? (
                  <>
                    {rateOfChange.losing ? '-' : '+'}{Math.abs(rateOfChange.kgPerWeek).toFixed(2)} kg/wk
                  </>
                ) : '\u2014'}
              </Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">Peak Week Est.</Text>
              <Text fw={700}>{peakWeekWeight ? displayWeight(peakWeekWeight, unit) : '\u2014'}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">Days to Confirm</Text>
              <Text
                fw={700}
                c={daysToConfirm !== null && daysToConfirm < 14 ? 'red' : undefined}
              >
                {daysToConfirm !== null ? daysToConfirm : '\u2014'}
              </Text>
            </div>
          </SimpleGrid>
        </Stack>
      </Paper>

      {/* Add Entry Form */}
      <Paper withBorder p="md" radius="md">
        <Text fw={500} mb="sm">Log Weight</Text>
        <Group gap="xs">
          <TextInput
            type="date"
            value={newDate}
            onChange={(e) => setNewDate(e.currentTarget.value)}
          />
          <TextInput
            type="number"
            flex={1}
            value={newWeight || ''}
            onChange={(e) => setNewWeight(e.currentTarget.value)}
            placeholder={unit}
            step={unit === 'kg' ? 0.1 : 0.25}
          />
          <ActionIcon
            variant="filled"
            size="lg"
            disabled={!newWeight || !newDate}
            onClick={handleAddEntry}
          >
            <Plus size={16} />
          </ActionIcon>
        </Group>
      </Paper>

      {/* Weight Log */}
      {sortedEntries.length > 0 && (
        <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
          <Paper bg="var(--mantine-color-default)" px="md" py="sm">
            <Group justify="space-between">
              <Text size="sm" fw={500}>History</Text>
              <Text size="xs" c="dimmed">{sortedEntries.length} entries</Text>
            </Group>
          </Paper>
          <div style={{ maxHeight: 520, overflowY: 'auto' }}>
            {sortedEntries
              .map((entry) => (
                <Group
                  key={entry.date}
                  justify="space-between"
                  px="md"
                  py="xs"
                  style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}
                >
                  <div>
                    <Text fw={500}>{formatDateShort(entry.date)}</Text>
                    <Text size="sm" c="dimmed">{entry.date}</Text>
                  </div>
                  <Group gap="sm">
                    <Text fw={700}>{displayWeight(entry.kg, unit)}</Text>
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      size="sm"
                      onClick={() => handleDeleteEntry(entry.date)}
                    >
                      <Trash2 size={14} />
                    </ActionIcon>
                  </Group>
                </Group>
              ))}
          </div>
        </Paper>
      )}

      {sortedEntries.length === 0 && (
        <Text c="dimmed" ta="center" py="xl">
          No weight entries yet. Start logging to track progress.
        </Text>
      )}
    </Stack>
  )
}
