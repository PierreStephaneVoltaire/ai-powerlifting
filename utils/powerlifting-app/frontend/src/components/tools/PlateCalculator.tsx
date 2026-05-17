import { useState, useMemo } from 'react'
import { useSettingsStore } from '@/store/settingsStore'
import { useProgramStore } from '@/store/programStore'
import { getPlateLoadout, closestLbLoadout, compAttempts, getPlateColor } from '@/utils/plates'
import { BAR_WEIGHTS_KG, type BarPreset } from '@/constants/plates'
import { displayWeight, kgToLb, toDisplayUnit } from '@/utils/units'
import {
  Paper,
  Button,
  Group,
  Stack,
  SimpleGrid,
  TextInput,
  Select,
  Table,
  Text,
  Title,
  SegmentedControl,
} from '@mantine/core'

type PlateMode = 'kg' | 'lb' | 'both'

export default function PlateCalculator() {
  const { unit, barWeightKg, setBarWeight } = useSettingsStore()
  const { program } = useProgramStore()
  const [targetWeight, setTargetWeight] = useState<number>(0)
  const [barPreset, setBarPreset] = useState<BarPreset>('standard')
  const [plateMode, setPlateMode] = useState<PlateMode>('kg')

  // Get bar weight from preset
  const actualBarWeight = barPreset === 'custom' ? barWeightKg : BAR_WEIGHTS_KG[barPreset]

  // Convert target weight to kg if in lb mode
  const targetKg = useMemo(() => {
    if (unit === 'lb') {
      return targetWeight / 2.20462 // lb to kg
    }
    return targetWeight
  }, [targetWeight, unit])

  // Calculate plate loadout
  const loadout = useMemo(() => {
    if (targetKg <= 0) return null
    return getPlateLoadout(targetKg, actualBarWeight)
  }, [targetKg, actualBarWeight])

  // Calculate LB loadout for comparison
  const lbLoadout = useMemo(() => {
    if (targetKg <= 0 || plateMode === 'lb' || plateMode === 'both') return null
    return closestLbLoadout(targetKg, actualBarWeight)
  }, [targetKg, actualBarWeight, plateMode])

  // Competition attempt suggestions
  const attempts = useMemo(() => {
    if (!program?.meta?.target_total_kg) return null
    return compAttempts(program.meta.target_total_kg)
  }, [program])

  // Quick presets from maxes
  const quickPresets = useMemo(() => {
    if (!program?.meta) return []
    const { target_squat_kg, target_bench_kg, target_dl_kg } = program.meta
    return [
      { label: 'Squat Target', kg: target_squat_kg },
      { label: 'Bench Target', kg: target_bench_kg },
      { label: 'DL Target', kg: target_dl_kg },
    ]
  }, [program])

  return (
    <Stack gap="xl">
      <div>
        <Title order={2} mb="sm">Plate Calculator</Title>
        <Text c="dimmed">
          Calculate how to load the barbell for your target weight
        </Text>
      </div>

      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
        {/* Target Weight Input */}
        <Stack gap="xs">
          <Text size="sm" fw={500}>Target Weight</Text>
          <Group gap="xs">
            <TextInput
              type="number"
              flex={1}
              value={targetWeight || ''}
              onChange={(e) => setTargetWeight(Number(e.currentTarget.value) || 0)}
              placeholder={unit === 'kg' ? 'kg' : 'lb'}
              step={unit === 'kg' ? 2.5 : 5}
              data-testid="plate-target-weight"
            />
            <Paper bg="var(--mantine-color-default)" px="sm" py="xs" radius="sm">
              <Text size="sm">{unit.toUpperCase()}</Text>
            </Paper>
          </Group>
        </Stack>

        {/* Bar Preset */}
        <Stack gap="xs">
          <Text size="sm" fw={500}>Bar Weight</Text>
          <Select
            data={[
              { value: 'standard', label: 'Standard (20kg)' },
              { value: 'womens', label: "Women's (15kg)" },
              { value: 'deadlift', label: 'Deadlift (25kg)' },
              { value: 'custom', label: 'Custom' },
            ]}
            value={barPreset}
            onChange={(val) => setBarPreset((val ?? 'standard') as BarPreset)}
            data-testid="plate-bar-preset"
          />
          {barPreset === 'custom' && (
            <TextInput
              type="number"
              value={barWeightKg || ''}
              onChange={(e) => setBarWeight(Number(e.currentTarget.value) || 20)}
              placeholder="kg"
              step={0.5}
            />
          )}
        </Stack>

        {/* Plate Mode */}
        <Stack gap="xs">
          <Text size="sm" fw={500}>Plate Mode</Text>
          <SegmentedControl
            fullWidth
            data={[
              { label: 'KG Plates', value: 'kg' },
              { label: 'LB Plates', value: 'lb' },
              { label: 'Both', value: 'both' },
            ]}
              value={plateMode}
              onChange={(val) => setPlateMode(val as PlateMode)}
              data-testid="plate-mode"
            />
        </Stack>
      </SimpleGrid>

      {/* Quick Presets */}
      {quickPresets && quickPresets.length > 0 && (
        <Stack gap="xs">
          <Text size="sm" fw={500}>Quick Presets</Text>
          <Group gap="xs">
            {quickPresets.map((preset) => (
              <Button
                key={preset.label}
                variant="default"
                size="xs"
                onClick={() => {
                  setTargetWeight(unit === 'kg' ? preset.kg : kgToLb(preset.kg))
                }}
              >
                {preset.label} ({displayWeight(preset.kg, unit)})
              </Button>
            ))}
          </Group>
        </Stack>
      )}

      {/* Results */}
      {loadout && (
        <Paper withBorder p="lg" radius="md">
          <Stack gap="xl">
            {/* Summary */}
            <Group justify="space-between" align="flex-start">
              <div>
                <Text size="sm" c="dimmed">Target</Text>
                <Text fz="h2" fw={700}>{displayWeight(targetKg, unit)}</Text>
              </div>
              <div style={{ textAlign: 'right' }}>
                <Text size="sm" c="dimmed">Achievable</Text>
                <Text
                  fz="h2"
                  fw={700}
                  c={loadout.achievable ? 'var(--mantine-color-blue-filled)' : 'var(--mantine-color-error)'}
                >
                  {displayWeight(loadout.totalKg, unit)}
                </Text>
              </div>
            </Group>

            {!loadout.achievable && (
              <Text size="sm" c="error">
                Cannot achieve exact weight. Remainder: {loadout.remainder.toFixed(2)} kg
              </Text>
            )}

            {/* Plate Visualization */}
            <Group justify="center" gap="sm" py="xl">
              {/* Left plates - smallest at edge, largest closest to bar */}
              <Group gap={4}>
                {[...loadout.plates].reverse().map((plate, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: 2,
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      width: `${Math.min(40 + plate * 2, 80)}px`,
                      height: `${Math.min(20 + plate, 40)}px`,
                      backgroundColor: getPlateColor(plate, plateMode === 'lb' ? 'lb' : 'kg'),
                      color: plate >= 5 ? '#fff' : '#000',
                    }}
                  >
                    {plate}
                  </div>
                ))}
              </Group>

              {/* Bar */}
              <div style={{ width: 16, height: 32, backgroundColor: '#9ca3af', borderRadius: 2 }} />

              {/* Right plates - largest closest to bar, smallest at edge */}
              <Group gap={4}>
                {loadout.plates.map((plate, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: 2,
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      width: `${Math.min(40 + plate * 2, 80)}px`,
                      height: `${Math.min(20 + plate, 40)}px`,
                      backgroundColor: getPlateColor(plate, plateMode === 'lb' ? 'lb' : 'kg'),
                      color: plate >= 5 ? '#fff' : '#000',
                    }}
                  >
                    {plate}
                  </div>
                ))}
              </Group>
            </Group>

            {/* Plate Table */}
            <Stack gap="xs">
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Plates (per side)</Table.Th>
                    <Table.Th ta="right">kg</Table.Th>
                    <Table.Th ta="right">lb</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {Array.from(new Set(loadout.plates)).sort((a, b) => b - a).map((plate) => {
                    const count = loadout.plates.filter((p) => p === plate).length
                    return (
                      <Table.Tr key={plate}>
                        <Table.Td>{count}x {plate}kg</Table.Td>
                        <Table.Td ta="right">{plate.toFixed(1)} kg</Table.Td>
                        <Table.Td ta="right">{kgToLb(plate).toFixed(1)} lb</Table.Td>
                      </Table.Tr>
                    )
                  })}
                  <Table.Tr fw={500}>
                    <Table.Td>Per side total</Table.Td>
                    <Table.Td ta="right">{loadout.perSideKg.toFixed(1)} kg</Table.Td>
                    <Table.Td ta="right">{kgToLb(loadout.perSideKg).toFixed(1)} lb</Table.Td>
                  </Table.Tr>
                  <Table.Tr fw={500} style={{ borderTopWidth: 2 }}>
                    <Table.Td>Bar</Table.Td>
                    <Table.Td ta="right">{actualBarWeight.toFixed(1)} kg</Table.Td>
                    <Table.Td ta="right">{kgToLb(actualBarWeight).toFixed(1)} lb</Table.Td>
                  </Table.Tr>
                  <Table.Tr fw={700} bg="var(--mantine-color-blue-light)">
                    <Table.Td>Grand Total</Table.Td>
                    <Table.Td ta="right" data-testid="plate-grand-total-kg">{loadout.totalKg.toFixed(1)} kg</Table.Td>
                    <Table.Td ta="right" data-testid="plate-grand-total-lb">{kgToLb(loadout.totalKg).toFixed(1)} lb</Table.Td>
                  </Table.Tr>
                </Table.Tbody>
              </Table>
            </Stack>

            {/* LB Mode Comparison */}
            {(plateMode === 'lb' || plateMode === 'both') && lbLoadout && (
              <Paper bg="var(--mantine-color-yellow-light)" p="md" radius="md">
                <Text size="sm">
                  <Text span fw={500}>With LB plates:</Text>{' '}
                  {displayWeight(lbLoadout.achievedKg, unit)}
                  {Math.abs(lbLoadout.deltaKg) > 0.1 && (
                    <Text span c="var(--mantine-color-yellow-7)" ml="xs">
                      (delta: {lbLoadout.deltaKg > 0 ? '+' : ''}{lbLoadout.deltaKg} kg)
                    </Text>
                  )}
                </Text>
              </Paper>
            )}
          </Stack>
        </Paper>
      )}

      {/* Competition Attempts */}
      {attempts && (
        <Paper withBorder p="lg" radius="md">
          <Text fw={500} mb="md">Competition Attempts</Text>
          <Text size="sm" c="dimmed" mb="md">
            Suggested attempts based on your target total ({displayWeight(program!.meta.target_total_kg, unit)})
          </Text>
          <SimpleGrid cols={3} spacing="md">
            <Paper bg="var(--mantine-color-default)" p="md" radius="md" ta="center">
              <Text size="sm" c="dimmed">Opener (85%)</Text>
              <Text fz="xl" fw={700}>{displayWeight(attempts.opener, unit)}</Text>
            </Paper>
            <Paper bg="var(--mantine-color-default)" p="md" radius="md" ta="center">
              <Text size="sm" c="dimmed">Second (95%)</Text>
              <Text fz="xl" fw={700}>{displayWeight(attempts.second, unit)}</Text>
            </Paper>
            <Paper bg="var(--mantine-color-blue-light)" p="md" radius="md" ta="center">
              <Text size="sm" c="dimmed">Third (100%)</Text>
              <Text fz="xl" fw={700} c="blue">{displayWeight(attempts.third, unit)}</Text>
            </Paper>
          </SimpleGrid>
        </Paper>
      )}
    </Stack>
  )
}
