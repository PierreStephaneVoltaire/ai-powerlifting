import { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Box,
  Group,
  Modal,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
} from '@mantine/core'
import { useSettingsStore } from '@/store/settingsStore'
import { closestLbLoadout, getPlateColor, getPlateLoadout } from '@/utils/plates'
import { displayWeight, fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { buildPercentRows, buildRpeRows, estimateSetE1rm } from '@/utils/rpe'
import { resolvePlateInventory } from '@/utils/plateInventory'
import PlateInventoryEditor from '@/components/tools/PlateInventoryEditor'

interface SessionToolkitModalProps {
  opened: boolean
  onClose: () => void
  exerciseName: string
  targetKg: number | null
  reps: number | null
  isBarbell: boolean
}

function plateDisplayValue(plateKg: number, unit: 'kg' | 'lb'): string {
  return unit === 'lb'
    ? parseFloat((plateKg * 2.20462).toFixed(2)).toString()
    : plateKg.toString()
}

export default function SessionToolkitModal({
  opened,
  onClose,
  exerciseName,
  targetKg,
  reps,
  isBarbell,
}: SessionToolkitModalProps) {
  const {
    unit,
    barWeightKg,
    plateInventoryKg,
    plateInventoryLb,
    setPlateInventoryKg,
    setPlateInventoryLb,
  } = useSettingsStore()

  const [weightKg, setWeightKg] = useState<number | null>(targetKg)
  const [barWeightKgInput, setBarWeightKgInput] = useState<number>(isBarbell ? barWeightKg : 0)
  const [repsInput, setRepsInput] = useState<number | null>(reps)
  const [rpeInput, setRpeInput] = useState<number | null>(8)

  useEffect(() => {
    if (!opened) return
    setWeightKg(targetKg)
    setBarWeightKgInput(isBarbell ? barWeightKg : 0)
    setRepsInput(reps)
    setRpeInput(8)
  }, [barWeightKg, isBarbell, opened, reps, targetKg])

  const inventory = unit === 'kg'
    ? resolvePlateInventory('kg', plateInventoryKg)
    : resolvePlateInventory('lb', plateInventoryLb)

  const loadoutResult = useMemo(() => {
    if (weightKg == null || !Number.isFinite(weightKg) || weightKg <= 0) return null
    const barWeightKg = Math.max(0, barWeightKgInput || 0)
    if (unit === 'kg') {
      const loadout = getPlateLoadout(weightKg, barWeightKg, inventory)
      return {
        loadout,
        remainderDisplay: loadout.remainder,
      }
    }
    const lbLoadout = closestLbLoadout(weightKg, barWeightKg, inventory)
    return {
      loadout: lbLoadout.loadout,
      remainderDisplay: toDisplayUnit(lbLoadout.loadout.remainder, unit),
    }
  }, [barWeightKgInput, inventory, unit, weightKg])

  const loadout = loadoutResult?.loadout ?? null
  const remainderText = loadoutResult ? loadoutResult.remainderDisplay.toFixed(2) : '0.00'

  const estimate = useMemo(() => {
    if (weightKg == null || repsInput == null) return null
    return estimateSetE1rm(weightKg, repsInput, rpeInput)
  }, [rpeInput, repsInput, weightKg])

  const percentRows = useMemo(() => {
    if (!estimate) return []
    return buildPercentRows(estimate.e1rmKg)
  }, [estimate])

  const rpeRows = useMemo(() => {
    if (!estimate || repsInput == null) return []
    return buildRpeRows(repsInput, estimate.e1rmKg)
  }, [estimate, repsInput])

  const currentPct = estimate ? estimate.pct * 100 : null
  const highlightedPercent = currentPct == null
    ? null
    : percentRows.reduce<{ pct: number; weightKg: number } | null>((best, row) => {
      if (!best) return row
      return Math.abs(row.pct - currentPct) < Math.abs(best.pct - currentPct) ? row : best
    }, null)

  const updateInventory = (plates: number[]) => {
    if (unit === 'kg') {
      setPlateInventoryKg(plates)
    } else {
      setPlateInventoryLb(plates)
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title={`${exerciseName} Toolkit`} size="xl" centered>
      <Tabs defaultValue="plates">
        <Tabs.List mb="md">
          <Tabs.Tab value="plates">Plates</Tabs.Tab>
          <Tabs.Tab value="rpe">RPE / %</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="plates">
          <Stack gap="md">
            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
              <Box>
                <Text size="sm" c="dimmed" mb={4}>Target Weight ({unit})</Text>
                <NumberInput
                  value={weightKg !== null ? toDisplayUnit(weightKg, unit) : ''}
                  onChange={(value) => setWeightKg(typeof value === 'number' ? fromDisplayUnit(value, unit) : null)}
                  min={0}
                  step={0.25}
                  decimalScale={2}
                  hideControls
                />
              </Box>

              <Box>
                <Text size="sm" c="dimmed" mb={4}>Bar Weight ({unit})</Text>
                <NumberInput
                  value={toDisplayUnit(barWeightKgInput, unit)}
                  onChange={(value) => setBarWeightKgInput(
                    typeof value === 'number' ? fromDisplayUnit(value, unit) : 0,
                  )}
                  min={0}
                  step={unit === 'kg' ? 0.25 : 0.5}
                  decimalScale={2}
                  hideControls
                />
                {!isBarbell && (
                  <Text size="xs" c="dimmed" mt={4}>
                    Non-barbell exercise defaulted to 0.
                  </Text>
                )}
              </Box>

              <Paper withBorder p="md" radius="md">
                <Text size="xs" c="dimmed">Inventory Unit</Text>
                <Badge mt={6} variant="light" size="sm">
                  {unit.toUpperCase()}
                </Badge>
                <Text size="xs" c="dimmed" mt={8}>
                  Store only the denominations you have. Counts are not tracked.
                </Text>
              </Paper>
            </SimpleGrid>

            <Paper withBorder p="md" radius="md">
              <PlateInventoryEditor
                unit={unit}
                plates={unit === 'kg' ? plateInventoryKg : plateInventoryLb}
                onChange={updateInventory}
                compact
              />
            </Paper>

            {!loadout ? (
              <Text size="sm" c="dimmed">
                Enter a target weight to calculate the loadout.
              </Text>
            ) : (
              <Stack gap="md">
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text size="sm" c="dimmed">Target</Text>
                    <Text fz="h2" fw={700}>{displayWeight(weightKg ?? 0, unit)}</Text>
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
                    Cannot achieve exact weight. Remainder: {remainderText} {unit}
                  </Text>
                )}

                <Group justify="center" gap="sm" py="md">
                  <div style={{ width: 16, height: 32, backgroundColor: '#9ca3af', borderRadius: 2 }} />

                  <Group gap={4}>
                    {loadout.plates.map((plate, idx) => (
                      <div
                        key={`right-${idx}`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderRadius: 2,
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          width: `${Math.min(40 + plate * 2, 80)}px`,
                          height: `${Math.min(20 + plate, 40)}px`,
                          backgroundColor: getPlateColor(plate, unit),
                          color: plate >= 5 ? '#fff' : '#000',
                        }}
                      >
                        {plateDisplayValue(plate, unit)}
                      </div>
                    ))}
                  </Group>
                </Group>

                <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
                  <Table>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Plates (per side)</Table.Th>
                        <Table.Th ta="right">{unit}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {Array.from(new Set(loadout.plates)).sort((a, b) => b - a).map((plate) => {
                        const count = loadout.plates.filter((p) => p === plate).length
                        return (
                          <Table.Tr key={plate}>
                            <Table.Td>{count}x {plateDisplayValue(plate, unit)}{unit}</Table.Td>
                            <Table.Td ta="right">{plateDisplayValue(plate, unit)} {unit}</Table.Td>
                          </Table.Tr>
                        )
                      })}
                      <Table.Tr fw={500}>
                        <Table.Td>Per side total</Table.Td>
                        <Table.Td ta="right">{displayWeight(loadout.perSideKg, unit)}</Table.Td>
                      </Table.Tr>
                      <Table.Tr fw={500} style={{ borderTopWidth: 2 }}>
                        <Table.Td>Bar</Table.Td>
                        <Table.Td ta="right">{displayWeight(Math.max(0, barWeightKgInput || 0), unit)}</Table.Td>
                      </Table.Tr>
                      <Table.Tr fw={700} bg="var(--mantine-color-blue-light)">
                        <Table.Td>Grand Total</Table.Td>
                        <Table.Td ta="right">{displayWeight(loadout.totalKg, unit)}</Table.Td>
                      </Table.Tr>
                    </Table.Tbody>
                  </Table>
                </Paper>
              </Stack>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="rpe">
          <Stack gap="md">
            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
              <Box>
                <Text size="sm" c="dimmed" mb={4}>Set Weight ({unit})</Text>
                <NumberInput
                  value={weightKg !== null ? toDisplayUnit(weightKg, unit) : ''}
                  onChange={(value) => setWeightKg(typeof value === 'number' ? fromDisplayUnit(value, unit) : null)}
                  min={0}
                  step={0.25}
                  decimalScale={2}
                  hideControls
                />
              </Box>

              <Box>
                <Text size="sm" c="dimmed" mb={4}>Reps</Text>
                <NumberInput
                  value={repsInput ?? ''}
                  onChange={(value) => setRepsInput(typeof value === 'number' ? value : null)}
                  min={0}
                  step={1}
                  hideControls
                />
              </Box>

              <Box>
                <Text size="sm" c="dimmed" mb={4}>RPE</Text>
                <NumberInput
                  value={rpeInput ?? ''}
                  onChange={(value) => setRpeInput(typeof value === 'number' ? value : null)}
                  min={6}
                  max={10}
                  step={0.5}
                  decimalScale={1}
                  hideControls
                />
              </Box>
            </SimpleGrid>

            {!estimate ? (
              <Text size="sm" c="dimmed">
                Enter a set weight and reps to estimate 1RM and build the table.
              </Text>
            ) : (
              <>
                <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
                  <Paper withBorder p="md" radius="md">
                    <Text size="xs" c="dimmed">Set Weight</Text>
                    <Text fw={700} fz="xl">{displayWeight(weightKg ?? 0, unit)}</Text>
                  </Paper>
                  <Paper withBorder p="md" radius="md">
                    <Text size="xs" c="dimmed">Estimated 1RM</Text>
                    <Text fw={700} fz="xl">{displayWeight(estimate.e1rmKg, unit)}</Text>
                  </Paper>
                  <Paper withBorder p="md" radius="md">
                    <Text size="xs" c="dimmed">Current % of 1RM</Text>
                    <Text fw={700} fz="xl">{currentPct?.toFixed(1)}%</Text>
                  </Paper>
                </SimpleGrid>

                <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
                  <Table>
                    <Table.Thead>
                      <Table.Tr bg="var(--mantine-color-default)">
                        <Table.Th>RPE</Table.Th>
                        <Table.Th ta="right">% of 1RM</Table.Th>
                        <Table.Th ta="right">Weight</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {rpeRows.map((row) => {
                        const isCurrent = rpeInput != null && Math.abs(row.rpe - rpeInput) < 0.001
                        return (
                          <Table.Tr
                            key={row.rpe}
                            bg={isCurrent ? 'var(--mantine-color-blue-light)' : undefined}
                            fw={isCurrent ? 700 : undefined}
                          >
                            <Table.Td>{row.rpe.toFixed(1)}</Table.Td>
                            <Table.Td ta="right">{(row.pct * 100).toFixed(1)}%</Table.Td>
                            <Table.Td ta="right">{displayWeight(row.weightKg, unit)}</Table.Td>
                          </Table.Tr>
                        )
                      })}
                    </Table.Tbody>
                  </Table>
                </Paper>

                <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
                  <Table>
                    <Table.Thead>
                      <Table.Tr bg="var(--mantine-color-default)">
                        <Table.Th>%</Table.Th>
                        <Table.Th ta="right">Weight</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {percentRows.map((row) => (
                        <Table.Tr
                          key={row.pct}
                          bg={highlightedPercent?.pct === row.pct ? 'var(--mantine-color-blue-light)' : undefined}
                          fw={highlightedPercent?.pct === row.pct ? 700 : undefined}
                        >
                          <Table.Td>{row.pct}%</Table.Td>
                          <Table.Td ta="right">{displayWeight(row.weightKg, unit)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Paper>

                <Text size="xs" c="dimmed">
                  The RPE table is an approximation anchored to the entered set. If the set is outside the usual low-rep range, treat the estimate as a helper rather than a hard prescription.
                </Text>
              </>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Modal>
  )
}
