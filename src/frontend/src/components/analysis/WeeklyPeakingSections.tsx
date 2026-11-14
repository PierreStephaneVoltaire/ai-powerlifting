import { AlertTriangle, Dumbbell, Info, TrendingUp, Trophy } from 'lucide-react'
import { Accordion, Badge, Box, Group, Paper, SimpleGrid, Stack, Table, Text, Tooltip } from '@mantine/core'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import type { WeeklyAnalysis } from '@/api/analytics'
import type { Competition } from '@powerlifting/types'
import { FORMULA_DESCRIPTIONS } from '@/constants/formulaDescriptions'
import { formatDisplayWeight } from '@/utils/units'
import type { Unit } from '@/store/settingsStore'
import { ChartLabel } from '@/components/analysis/ChartLabel'
import { PeakingTimeline } from '@/components/analysis/PeakingTimeline'

function isInsufficientData(value: unknown): value is { status: 'insufficient_data'; reason: string } {
  return !!value && typeof value === 'object' && 'status' in value
}

function compStatusBadge(status: string) {
  const colors: Record<string, string> = {
    confirmed: 'green',
    optional: 'blue',
    completed: 'gray',
    skipped: 'gray',
  }
  return <Badge variant="light" color={colors[status] || 'gray'} size="sm">{status}</Badge>
}

function banisterBadgeColor(tsb: number) {
  if (tsb < -30) return 'red'
  if (tsb < -10) return 'orange'
  if (tsb <= 5) return 'yellow'
  if (tsb <= 15) return 'green'
  return 'gray'
}

function decouplingBadgeColor(value: number) {
  if (value < 0) return 'red'
  if (value < 5) return 'yellow'
  return 'green'
}

function taperQualityBadgeColor(label: string) {
  if (label === 'excellent') return 'green'
  if (label === 'good') return 'blue'
  if (label === 'acceptable') return 'yellow'
  return 'red'
}

function volumeConfidenceColor(confidence?: string) {
  if (confidence === 'high') return 'green'
  if (confidence === 'medium') return 'blue'
  if (confidence === 'low') return 'yellow'
  return 'gray'
}

function InfoLabel({ label, help }: { label: string; help: string }) {
  return (
    <Group gap={4} justify="center" wrap="nowrap">
      <Text fz="xs" c="dimmed">{label}</Text>
      <Tooltip label={help} withArrow multiline w={260}>
        <Info size={12} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
      </Tooltip>
    </Group>
  )
}

export function AnalysisFlags({ flags }: { flags: string[] }) {
  return (
    <>
      {flags.length > 0 && (
        <Paper withBorder p="md" className="if-card">
          <Group gap="xs" mb="sm">
            <AlertTriangle size={18} color="var(--mantine-color-yellow-5)" />
            <Text fw={500}>Flags</Text>
          </Group>
          <Group gap="xs" wrap="wrap">
            {flags.map(flag => (
              <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
            ))}
          </Group>
        </Paper>
      )}
    </>
  )
}

export function PeakingSection({
  data,
  banisterSeries,
  upcomingCompetition,
}: {
  data: WeeklyAnalysis
  banisterSeries: Array<{ date: string; ctl: number; atl: number; tsb: number }>
  upcomingCompetition: Competition | null
}) {
  const banister = data.banister && !isInsufficientData(data.banister) ? data.banister : null
  const decoupling = data.decoupling && !isInsufficientData(data.decoupling) ? data.decoupling : null
  const taperQuality = data.taper_quality && !isInsufficientData(data.taper_quality) ? data.taper_quality : null
  const peakingTimeline = data.peaking_timeline ?? null

  return (
    <>
      {(data.banister || data.decoupling || taperQuality) && (
        <Stack gap="md">
          <Paper withBorder p="md" className="if-card">
            <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
              <Group gap="xs">
                <TrendingUp size={18} />
                <Text fw={500}>Form / Peaking Readiness</Text>
                <ChartLabel text="TSB is CTL minus ATL. Peak form is +5 to +15." />
              </Group>
              {banister && (
                <Badge variant="light" color={banisterBadgeColor(banister.tsb_today)} size="sm">
                  {banister.tsb_label}
                </Badge>
              )}
            </Group>

            {banister ? (
              <Stack gap="md">
                <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                  <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-orange-light)' }}>
                    <InfoLabel label="CTL / Fitness" help="Chronic training load. A longer-horizon fitness signal built from your recent workload history." />
                    <Text fz="xl" fw={700} c="var(--mantine-color-text)">{banister.ctl_today.toFixed(1)}</Text>
                  </Stack>
                  <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-red-light)' }}>
                    <InfoLabel label="ATL / Fatigue" help="Acute training load. A shorter-horizon fatigue signal that reacts faster to recent hard training." />
                    <Text fz="xl" fw={700} c="var(--mantine-color-text)">{banister.atl_today.toFixed(1)}</Text>
                  </Stack>
                  <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-blue-light)' }}>
                    <InfoLabel label="TSB / Form" help="Training stress balance. CTL minus ATL. Higher values usually mean fresher; very negative values usually mean accumulated fatigue." />
                    <Text fz="xl" fw={700} c={banisterBadgeColor(banister.tsb_today)}>{banister.tsb_today.toFixed(1)}</Text>
                  </Stack>
                </SimpleGrid>

                {banisterSeries.length > 0 ? (
                  <>
                    <Box style={{ width: '100%', height: 320 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={banisterSeries}>
                          <CartesianGrid
                            strokeDasharray="3 3"
                            vertical={false}
                            stroke="var(--mantine-color-default-border)"
                          />
                          <XAxis
                            dataKey="date"
                            tickFormatter={(value) => String(value).slice(5)}
                            minTickGap={18}
                            tick={{ fill: 'var(--mantine-color-dimmed)' }}
                            axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                            tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                          />
                          <YAxis
                            tick={{ fill: 'var(--mantine-color-dimmed)' }}
                            axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                            tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                          />
                          <RechartsTooltip
                            labelFormatter={(label) => `Date: ${String(label)}`}
                            contentStyle={{
                              backgroundColor: 'var(--mantine-color-body)',
                              border: '1px solid var(--mantine-color-default-border)',
                              color: 'var(--mantine-color-text)',
                            }}
                            labelStyle={{ color: 'var(--mantine-color-text)' }}
                            itemStyle={{ color: 'var(--mantine-color-text)' }}
                          />
                          <Legend />
                          <Line type="monotone" dataKey="ctl" name="CTL" stroke="#f59e0b" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="atl" name="ATL" stroke="#ef4444" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="tsb" name="TSB" stroke="#3b82f6" strokeWidth={2} dot={false} />
                          {upcomingCompetition && (
                            <ReferenceLine
                              x={upcomingCompetition.date}
                              stroke="var(--mantine-color-dimmed)"
                              strokeDasharray="4 4"
                              label={{ value: 'Comp', position: 'insideTopRight' }}
                            />
                          )}
                        </LineChart>
                      </ResponsiveContainer>
                    </Box>
                    {upcomingCompetition && (
                      <Text fz="xs" c="dimmed">
                        Competition marker: {upcomingCompetition.name} on {upcomingCompetition.date}
                      </Text>
                    )}
                  </>
                ) : (
                  <Text fz="sm" c="dimmed">No Banister datapoints fall inside the selected window.</Text>
                )}
              </Stack>
            ) : (
              <Text fz="sm" c="dimmed">
                {isInsufficientData(data.banister) ? data.banister.reason : 'No Banister data available.'}
              </Text>
          )}
        </Paper>

        {peakingTimeline && (
          <PeakingTimeline data={peakingTimeline} />
        )}

          <SimpleGrid cols={{ base: 1, lg: taperQuality ? 2 : 1 }} spacing="md">
            <Paper withBorder p="md" className="if-card">
              <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
                <Group gap="xs">
                  <Dumbbell size={18} />
                  <Text fw={500}>Strength-Fatigue Decoupling</Text>
                </Group>
                {decoupling && decoupling.current && (
                  <Badge variant="light" color={decouplingBadgeColor(decoupling.current.decoupling)} size="sm">
                    {decoupling.current.decoupling >= 0 ? 'Positive' : 'Negative'}
                  </Badge>
                )}
              </Group>

              {decoupling ? (
                <Stack gap="sm">
                  {decoupling.current ? (
                    <>
                      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                        <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">Decoupling</Text>
                          <Text fz="xl" fw={700} c={decouplingBadgeColor(decoupling.current.decoupling)}>
                            {decoupling.current.decoupling.toFixed(2)}
                          </Text>
                        </Stack>
                        <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">e1RM slope</Text>
                          <Text fz="xl" fw={700} c={decoupling.current.e1rm_slope_pct_per_week >= 0 ? 'green' : 'red'}>
                            {decoupling.current.e1rm_slope_pct_per_week >= 0 ? '+' : ''}{decoupling.current.e1rm_slope_pct_per_week.toFixed(2)}%/wk
                          </Text>
                        </Stack>
                        <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">Fatigue slope</Text>
                          <Text fz="xl" fw={700} c={decoupling.current.fi_slope_pct_points_per_week <= 0 ? 'green' : 'red'}>
                            {decoupling.current.fi_slope_pct_points_per_week >= 0 ? '+' : ''}{decoupling.current.fi_slope_pct_points_per_week.toFixed(2)} pp/wk
                          </Text>
                        </Stack>
                      </SimpleGrid>
                      {decoupling.flags.length > 0 && (
                        <Group gap="xs" wrap="wrap">
                          {decoupling.flags.map(flag => (
                            <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
                          ))}
                        </Group>
                      )}
                      {decoupling.series.length > 0 && (
                        <Box style={{ overflowX: 'auto' }}>
                          <Table fz="sm">
                            <Table.Thead>
                              <Table.Tr>
                                <Table.Th>Week Start</Table.Th>
                                <Table.Th ta="right">Decoupling</Table.Th>
                              </Table.Tr>
                            </Table.Thead>
                            <Table.Tbody>
                              {decoupling.series.slice(-4).map(point => (
                                <Table.Tr key={point.week_start}>
                                  <Table.Td fw={500}>{point.week_start}</Table.Td>
                                  <Table.Td ta="right" c={decouplingBadgeColor(point.decoupling)}>
                                    {point.decoupling >= 0 ? '+' : ''}{point.decoupling.toFixed(2)}
                                  </Table.Td>
                                </Table.Tr>
                              ))}
                            </Table.Tbody>
                          </Table>
                        </Box>
                      )}
                    </>
                  ) : (
                    <Text fz="sm" c="dimmed">No decoupling window available yet.</Text>
                  )}
                </Stack>
              ) : (
                <Text fz="sm" c="dimmed">
                  {isInsufficientData(data.decoupling) ? data.decoupling.reason : 'No decoupling data available.'}
                </Text>
              )}
            </Paper>

            {taperQuality && (
              <Paper withBorder p="md" className="if-card">
                <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
                  <Group gap="xs">
                    <Trophy size={18} />
                    <Text fw={500}>Taper Quality Score</Text>
                  </Group>
                  <Badge variant="light" color={taperQualityBadgeColor(taperQuality.label)} size="sm">
                    {taperQuality.label}
                  </Badge>
                </Group>

                <Stack gap="sm">
                  <Group align="baseline" gap="sm">
                    <Text fz="2rem" fw={700}>{taperQuality.score.toFixed(0)}</Text>
                    <Text fz="sm" c="dimmed">/ 100</Text>
                  </Group>
                  <Text fz="xs" c="dimmed">Weeks to comp: {taperQuality.weeks_to_comp.toFixed(1)}</Text>
                  <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                    <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                      <Text fz="xs" c="dimmed">Volume</Text>
                      <Text fz="lg" fw={700}>{(taperQuality.components.volume_reduction * 100).toFixed(0)}%</Text>
                    </Stack>
                    <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                      <Text fz="xs" c="dimmed">Intensity</Text>
                      <Text fz="lg" fw={700}>{(taperQuality.components.intensity_maintained * 100).toFixed(0)}%</Text>
                    </Stack>
                    <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                      <Text fz="xs" c="dimmed">Fatigue Trend</Text>
                      <Text fz="lg" fw={700}>{(taperQuality.components.fatigue_trend * 100).toFixed(0)}%</Text>
                    </Stack>
                    <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                      <Text fz="xs" c="dimmed">TSB</Text>
                      <Text fz="lg" fw={700}>{(taperQuality.components.tsb * 100).toFixed(0)}%</Text>
                    </Stack>
                  </SimpleGrid>
                </Stack>
              </Paper>
            )}
          </SimpleGrid>
        </Stack>
      )}
    </>
  )
}

export function VolumeLandmarksSection({ data }: { data: WeeklyAnalysis }) {
  const volumeLandmarkEntries = data.volume_landmarks
    ? (Object.entries(data.volume_landmarks).filter(([, value]) => !isInsufficientData(value)) as Array<[string, any]>)
    : []

  return (
    <>
      {volumeLandmarkEntries.length > 0 && (
        <Paper withBorder p="md" className="if-card">
          <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
            <Group gap="xs">
              <Dumbbell size={18} />
              <Text fw={500}>Volume Landmarks</Text>
            </Group>
            <Text fz="xs" c="dimmed">MEV / MAV / MRV from whole-program history</Text>
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            {volumeLandmarkEntries.map(([lift, landmark]) => (
              <Stack
                key={lift}
                gap="xs"
                p="sm"
                style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}
              >
                <Group justify="space-between" align="center">
                  <Text fw={500} tt="capitalize">{lift}</Text>
                  <Badge variant="light" color={volumeConfidenceColor(landmark.confidence)}>
                    {landmark.confidence}
                  </Badge>
                </Group>
                <Group justify="space-between">
                  <Text fz="xs" c="dimmed">MV</Text>
                  <Text fz="sm" fw={700}>{landmark.mv !== null ? `${landmark.mv.toFixed(1)} sets` : '--'}</Text>
                </Group>
                <Group justify="space-between">
                  <Text fz="xs" c="dimmed">MEV</Text>
                  <Text fz="sm" fw={700}>{landmark.mev !== null ? `${landmark.mev.toFixed(1)} sets` : '--'}</Text>
                </Group>
                <Group justify="space-between">
                  <Text fz="xs" c="dimmed">MAV</Text>
                  <Text fz="sm" fw={700}>{landmark.mav !== null ? `${landmark.mav.toFixed(1)} sets` : '--'}</Text>
                </Group>
                <Group justify="space-between">
                  <Text fz="xs" c="dimmed">MRV</Text>
                  <Text fz="sm" fw={700}>{landmark.mrv !== null ? `${landmark.mrv.toFixed(1)} sets` : '--'}</Text>
                </Group>
              </Stack>
            ))}
          </SimpleGrid>
        </Paper>
      )}
    </>
  )
}

export function CompetitionsSection({ competitions, unit }: { competitions: Competition[]; unit: Unit }) {
  return (
    <>
      {competitions.length > 0 && (
        <Paper withBorder p="md" className="if-card">
          <Group gap="xs" mb="sm">
            <Trophy size={18} />
            <Text fw={500}>Competitions</Text>
          </Group>
          <Box style={{ overflowX: 'auto' }}>
            <Table fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Date</Table.Th>
                  <Table.Th visibleFrom="sm">Status</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Squat</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Bench</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Deadlift</Table.Th>
                  <Table.Th ta="right">Total</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {competitions.map(c => (
                  <Table.Tr key={c.date + c.name}>
                    <Table.Td fw={500}>{c.name}</Table.Td>
                    <Table.Td c="dimmed">{c.date}</Table.Td>
                    <Table.Td visibleFrom="sm">{compStatusBadge(c.status)}</Table.Td>
                    {c.results ? (
                      <>
                        <Table.Td ta="right" visibleFrom="sm">{formatDisplayWeight(c.results.squat_kg, unit)}</Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">{formatDisplayWeight(c.results.bench_kg, unit)}</Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">{formatDisplayWeight(c.results.deadlift_kg, unit)}</Table.Td>
                        <Table.Td ta="right" fw={700}>{formatDisplayWeight(c.results.total_kg, unit)}</Table.Td>
                      </>
                    ) : (
                      <>
                        <Table.Td ta="right" c="dimmed" visibleFrom="sm">--</Table.Td>
                        <Table.Td ta="right" c="dimmed" visibleFrom="sm">--</Table.Td>
                        <Table.Td ta="right" c="dimmed" visibleFrom="sm">--</Table.Td>
                        <Table.Td ta="right" c="dimmed">--</Table.Td>
                      </>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Box>
        </Paper>
      )}
    </>
  )
}

export function FormulaReference() {
  return (
    <>
      <Accordion mt="xl" variant="separated" defaultValue="formulas-outer">
        <Accordion.Item value="formulas-outer">
          <Accordion.Control>
            <Text size="sm" fw={500} c="dimmed">How These Numbers Are Calculated</Text>
          </Accordion.Control>
          <Accordion.Panel>
            <Accordion variant="contained">
              {FORMULA_DESCRIPTIONS.map(formula => (
                <Accordion.Item
                  key={formula.id}
                  value={formula.id}
                  id={`formula-${formula.id}`}
                  style={{ scrollMarginTop: '6rem' }}
                >
                  <Accordion.Control>
                    <Text size="sm" fw={500}>{formula.title}</Text>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="xs">
                      <Text size="sm">{formula.summary}</Text>
                      <Box component="pre" fz="xs" p="sm" style={{ background: 'var(--mantine-color-dark-8, #1a1b1e)', borderRadius: 'var(--mantine-radius-sm)', overflowX: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{formula.formula}</Box>
                      {formula.variables && (
                        <SimpleGrid cols={2} spacing="xs">
                          {formula.variables.map(v => (
                            <Text key={v.name} size="xs"><Text span ff="monospace">{v.name}</Text>: {v.description}</Text>
                          ))}
                        </SimpleGrid>
                      )}
                      {formula.thresholds && (
                        <Table fz="xs" mt="xs">
                          <Table.Thead><Table.Tr><Table.Th ta="left">Condition</Table.Th><Table.Th ta="left">Value</Table.Th><Table.Th ta="left">Flag</Table.Th></Table.Tr></Table.Thead>
                          <Table.Tbody>{formula.thresholds.map(t => <Table.Tr key={t.label}><Table.Td>{t.label}</Table.Td><Table.Td>{t.value}</Table.Td><Table.Td>{t.flag || '—'}</Table.Td></Table.Tr>)}</Table.Tbody>
                        </Table>
                      )}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              ))}
            </Accordion>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </>
  )
}
