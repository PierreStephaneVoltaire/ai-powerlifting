import { useState, useEffect } from 'react'
import { Stack, Title, Paper, Text, SimpleGrid, TextInput, Group, Loader, Center, Switch, Divider, Badge } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { updateMetaField } from '@/api/client'
import { Trophy, ArrowUpCircle, Percent } from 'lucide-react'

interface LiftSettings {
  max: number;
  incremental: boolean;
  increment: number;
}

export default function AttemptSelector() {
  const { program, version } = useProgramStore()
  const [loading, setLoading] = useState(false)
  
  const [maxes, setMaxes] = useState({ squat: 0, bench: 0, deadlift: 0 })
  const [liftSettings, setLiftSettings] = useState<Record<string, LiftSettings>>({
    squat: { max: 0, incremental: false, increment: 5 },
    bench: { max: 0, incremental: false, increment: 5 },
    deadlift: { max: 0, incremental: false, increment: 5 },
  })
  
  const [attemptPct, setAttemptPct] = useState({ opener: 0.90, second: 0.955, third: 1.00 })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (program?.meta) {
      const metaMaxes = program.meta.manual_maxes || { squat: 0, bench: 0, deadlift: 0 }
      const metaSettings = program.meta.lift_attempt_settings || {
        squat: { max: metaMaxes.squat, incremental: false, increment: 5 },
        bench: { max: metaMaxes.bench, incremental: false, increment: 5 },
        deadlift: { max: metaMaxes.deadlift, incremental: false, increment: 5 },
      }
      const metaPct = program.meta.attempt_pct || { opener: 0.90, second: 0.955, third: 1.00 }
      
      setMaxes(metaMaxes)
      setLiftSettings(metaSettings)
      setAttemptPct(metaPct)
    }
  }, [program?.meta])

  const handleUpdateSetting = async (lift: string, field: keyof LiftSettings, value: any) => {
    const nextSettings = {
      ...liftSettings,
      [lift]: { ...liftSettings[lift], [field]: value }
    }
    setLiftSettings(nextSettings)
    
    // Auto-save to meta
    setSaving(true)
    try {
      await updateMetaField(version, 'lift_attempt_settings', nextSettings)
      if (field === 'max') {
        const nextMaxes = { ...maxes, [lift]: value }
        setMaxes(nextMaxes)
        await updateMetaField(version, 'manual_maxes', nextMaxes)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleUpdatePct = async (field: keyof typeof attemptPct, value: number) => {
    const nextPct = { ...attemptPct, [field]: value }
    setAttemptPct(nextPct)
    setSaving(true)
    try {
      await updateMetaField(version, 'attempt_pct', nextPct)
    } finally {
      setSaving(false)
    }
  }

  const calculateAttempts = (lift: string) => {
    const s = liftSettings[lift]
    if (!s.max) return { opener: 0, second: 0, third: 0 }
    
    if (s.incremental) {
      return {
        opener: Math.round((s.max - s.increment * 2) * 2) / 2,
        second: Math.round((s.max - s.increment) * 2) / 2,
        third: Math.round(s.max * 2) / 2
      }
    } else {
      return {
        opener: Math.round((s.max * attemptPct.opener) * 2) / 2,
        second: Math.round((s.max * attemptPct.second) * 2) / 2,
        third: Math.round((s.max * attemptPct.third) * 2) / 2
      }
    }
  }

  const results = {
    squat: calculateAttempts('squat'),
    bench: calculateAttempts('bench'),
    deadlift: calculateAttempts('deadlift'),
  }

  const total = results.squat.third + results.bench.third + results.deadlift.third

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Attempt Selector</Title>
        {saving && <Badge variant="dot" size="sm">Saving...</Badge>}
      </Group>
      
      <Paper withBorder p="md">
        <Group gap="xs" mb="md">
          <Percent size={18} />
          <Text fw={500}>Global Multipliers (Decimal)</Text>
        </Group>
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
          {[
            { key: 'opener' as const, label: 'Opener Pct', hint: 'Default 0.90' },
            { key: 'second' as const, label: 'Second Pct', hint: 'Default 0.955' },
            { key: 'third' as const, label: 'Third Pct', hint: 'Default 1.00' },
          ].map(({ key, label, hint }) => (
            <TextInput
              key={key}
              type="number"
              label={label}
              size="sm"
              value={attemptPct[key]}
              onChange={(e) => handleUpdatePct(key, Number(e.currentTarget.value))}
              step={0.005}
              description={hint}
            />
          ))}
        </SimpleGrid>
      </Paper>

      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
        {['squat', 'bench', 'deadlift'].map((lift) => (
          <Paper key={lift} withBorder p="md">
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={700} tt="capitalize">{lift}</Text>
                <Switch
                  label="Incremental"
                  size="xs"
                  checked={liftSettings[lift].incremental}
                  onChange={(e) => handleUpdateSetting(lift, 'incremental', e.currentTarget.checked)}
                />
              </Group>

              <TextInput
                type="number"
                label="Target Max (kg)"
                value={liftSettings[lift].max || ''}
                onChange={(e) => handleUpdateSetting(lift, 'max', Number(e.currentTarget.value) || 0)}
                placeholder="Target Max"
                step={0.5}
              />

              {liftSettings[lift].incremental && (
                <TextInput
                  type="number"
                  label="Increment (kg)"
                  value={liftSettings[lift].increment}
                  onChange={(e) => handleUpdateSetting(lift, 'increment', Number(e.currentTarget.value) || 5)}
                  step={0.5}
                  placeholder="kg per attempt"
                />
              )}

              <Divider my="xs" />

              <Stack gap={4}>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">Opener:</Text>
                  <Text fw={700}>{results[lift as keyof typeof results].opener} kg</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">Second:</Text>
                  <Text fw={700}>{results[lift as keyof typeof results].second} kg</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">Third:</Text>
                  <Text fw={700}>{results[lift as keyof typeof results].third} kg</Text>
                </Group>
              </Stack>
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>

      <Paper withBorder p="md" bg="var(--mantine-color-blue-light)">
        <Group justify="center">
          <Trophy size={24} color="var(--mantine-color-blue-filled)" />
          <Stack gap={0} align="center">
            <Text fz="xs" tt="uppercase" fw={700} c="dimmed">Projected Total</Text>
            <Text fz="2rem" fw={900}>{total.toFixed(1)} kg</Text>
          </Stack>
        </Group>
      </Paper>
    </Stack>
  )
}

