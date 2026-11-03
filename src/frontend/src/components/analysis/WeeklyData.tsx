import { Fragment, useState } from 'react';
import { Paper, Text, Box, Table, Group, Button, Badge, SimpleGrid, Stack, Tooltip as MantineTooltip } from '@mantine/core';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip as RechartsTooltip, BarChart, Bar, CartesianGrid, XAxis, YAxis } from 'recharts';
import type { WeeklyAnalysis } from '@/api/analytics';
import { toDisplayUnit } from '@/utils/units';
import { Unit } from '@/store/settingsStore';
import { MuscleWorkloadMap } from '@/components/analysis/MuscleWorkloadMap';

const CHART_COLORS = [
  '#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
];

function rpeTrendIcon(trend?: string) {
  if (!trend) return null;
  if (trend === 'up') return <Text span size="xs" fw={500} c="red">&#9650; rising</Text>;
  if (trend === 'down') return <Text span size="xs" fw={500} c="green">&#9660; improving</Text>;
  return <Text span size="xs" fw={500} c="dimmed">&#9644; stable</Text>;
}

interface WeeklyDataProps {
  data: WeeklyAnalysis;
  viewMode: 'raw' | 'graph';
  perLiftDetails: Record<string, { frequency: number; raw_sets: number; accessories: { name: string; sets: number; volume: number }[] }>;
  muscleGroupAvgWeekly: { sets: Record<string, number>; volume: Record<string, number> };
  analysisWeeks: number;
  unit: Unit;
}

export function WeeklyData({ data, viewMode, perLiftDetails, muscleGroupAvgWeekly, analysisWeeks, unit }: WeeklyDataProps) {
  const [expandedLifts, setExpandedLifts] = useState<Set<string>>(new Set());

  return (
    <>
      {/* Per-lift breakdown */}
      {Object.keys(data.lifts).length > 0 && (
        <Paper withBorder p="md">
          <Text fw={500} mb="sm">Per-Lift Breakdown</Text>
          <Box style={{ overflowX: 'auto' }}>
            <Table fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Exercise</Table.Th>
                  <Table.Th ta="right">Freq</Table.Th>
                  <Table.Th ta="right">Sets</Table.Th>
                  <Table.Th ta="right">Progression</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Fit Quality</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Volume %</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Intensity %</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">Failed</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">RPE Trend</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {Object.entries(data.lifts).map(([name, lift]) => {
                  const liftKey = name.toLowerCase().replace(' press', '');
                  const details = perLiftDetails[liftKey];
                  const isExpanded = expandedLifts.has(name);
                  return (
                    <Fragment key={name}>
                      <Table.Tr>
                        <Table.Td fw={500}>
                          <Group gap="xs">
                            {name}
                            {details && details.accessories.length > 0 && (
                              <Button
                                variant="subtle"
                                size="compact-xs"
                                color="gray"
                                onClick={() => setExpandedLifts(prev => {
                                  const next = new Set(prev);
                                  if (next.has(name)) next.delete(name); else next.add(name);
                                  return next;
                                })}
                              >
                                {isExpanded ? '▼' : '▶'} {details.accessories.length} acc
                              </Button>
                            )}
                          </Group>
                        </Table.Td>
                        <Table.Td ta="right">{details ? <Text span fz="sm">{details.frequency}/wk</Text> : <Text span fz="sm" c="dimmed">--</Text>}</Table.Td>
                        <Table.Td ta="right">{details ? <Text span fz="sm">{details.raw_sets}</Text> : <Text span fz="sm" c="dimmed">--</Text>}</Table.Td>
                        <Table.Td ta="right">
                          {lift.progression_rate_kg_per_week !== undefined && lift.progression_rate_kg_per_week !== null
                            ? <Text span fz="sm" c={lift.progression_rate_kg_per_week >= 0 ? 'green' : 'red'}>{lift.progression_rate_kg_per_week >= 0 ? '+' : ''}{toDisplayUnit(lift.progression_rate_kg_per_week, unit).toFixed(1)} {unit}/wk</Text>
                            : <Text span fz="sm" c="dimmed">--</Text>}
                        </Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">
                          {(() => {
                            const fitQuality = lift.fit_quality ?? lift.r_squared ?? lift.r2
                            const kendallTau = lift.kendall_tau
                            if (fitQuality === undefined || fitQuality === null) {
                              return <Text span fz="sm" c="dimmed">--</Text>
                            }
                            const label = kendallTau !== undefined && kendallTau !== null
                              ? `Kendall tau: ${kendallTau.toFixed(2)}`
                              : 'Kendall tau unavailable'
                            return (
                              <MantineTooltip label={label} withArrow>
                                <Text span fz="sm" c="dimmed">{(fitQuality * 100).toFixed(0)}%</Text>
                              </MantineTooltip>
                            )
                          })()}
                        </Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">
                          {lift.volume_change_pct !== undefined
                            ? <Text span fz="sm" c={lift.volume_change_pct >= 0 ? 'green' : 'red'}>{lift.volume_change_pct >= 0 ? '+' : ''}{lift.volume_change_pct.toFixed(0)}%</Text>
                            : <Text span fz="sm" c="dimmed">--</Text>}
                        </Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">
                          {lift.intensity_change_pct !== undefined
                            ? <Text span fz="sm" c={lift.intensity_change_pct >= 0 ? 'green' : 'red'}>{lift.intensity_change_pct >= 0 ? '+' : ''}{lift.intensity_change_pct.toFixed(0)}%</Text>
                            : <Text span fz="sm" c="dimmed">--</Text>}
                        </Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">
                          {lift.failed_sets !== undefined && lift.failed_sets > 0
                            ? <Badge variant="light" color="red" size="sm">{lift.failed_sets}</Badge>
                            : <Text span fz="sm" c="dimmed">0</Text>}
                        </Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">{rpeTrendIcon(lift.rpe_trend) || <Text span fz="sm" c="dimmed">--</Text>}</Table.Td>
                      </Table.Tr>
                      {isExpanded && details && details.accessories.length > 0 && (
                        <Table.Tr>
                          <Table.Td colSpan={9}>
                            <Box ml="md">
                              <Text fz="xs" c="dimmed" mb="xs">Accessory / Secondary Work</Text>
                              <SimpleGrid cols={{ base: 2, md: 3, lg: 4 }}>
                                {details.accessories.map(a => (
                                  <Box key={a.name} p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default)' }}>
                                    <Text fz="xs" fw={500}>{a.name}</Text>
                                    <Text fz="xs" c="dimmed">{a.sets} sets · {Math.round(toDisplayUnit(a.volume, unit)).toLocaleString()} {unit}</Text>
                                  </Box>
                                ))}
                              </SimpleGrid>
                            </Box>
                          </Table.Td>
                        </Table.Tr>
                      )}
                    </Fragment>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Box>
        </Paper>
      )}

      {/* Exercise Stats */}
      {data.exercise_stats && Object.keys(data.exercise_stats).length > 0 && (
        <Paper withBorder p="md">
          <Text fw={500} mb="sm">Exercise Volume</Text>
          {viewMode === 'raw' ? (
            <Box style={{ overflowX: 'auto' }}>
              <Table fz="sm">
                <Table.Thead><Table.Tr><Table.Th>Exercise</Table.Th><Table.Th ta="right">Total Sets</Table.Th><Table.Th ta="right">Volume ({unit})</Table.Th><Table.Th ta="right">Max ({unit})</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {Object.entries(data.exercise_stats)
                    .sort((a, b) => b[1].total_volume - a[1].total_volume)
                    .map(([name, s]) => (
                      <Table.Tr key={name}>
                        <Table.Td fw={500}>{name}</Table.Td>
                        <Table.Td ta="right">{s.total_sets}</Table.Td>
                        <Table.Td ta="right">{Math.round(toDisplayUnit(s.total_volume, unit)).toLocaleString()}</Table.Td>
                        <Table.Td ta="right">{toDisplayUnit(s.max_kg, unit).toFixed(1)}</Table.Td>
                      </Table.Tr>
                    ))}
                </Table.Tbody>
              </Table>
            </Box>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
              <Box>
                <Text fz="xs" c="dimmed" ta="center" mb="xs">Sets Distribution</Text>
                <ResponsiveContainer width="100%" height={350}>
                  <PieChart>
                    <Pie data={Object.entries(data.exercise_stats).sort((a, b) => b[1].total_sets - a[1].total_sets).slice(0, 10).map(([name, s], i) => ({ name, value: s.total_sets, fill: CHART_COLORS[i % CHART_COLORS.length] }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
                      {Object.entries(data.exercise_stats).sort((a, b) => b[1].total_sets - a[1].total_sets).slice(0, 10).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Pie>
                    <RechartsTooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
              <Box>
                <Text fz="xs" c="dimmed" ta="center" mb="xs">Volume Distribution</Text>
                <ResponsiveContainer width="100%" height={350}>
                  <PieChart>
                    <Pie data={Object.entries(data.exercise_stats).sort((a, b) => b[1].total_volume - a[1].total_volume).slice(0, 10).map(([name, s], i) => ({ name, value: toDisplayUnit(s.total_volume, unit), fill: CHART_COLORS[i % CHART_COLORS.length] }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
                      {Object.entries(data.exercise_stats).sort((a, b) => b[1].total_volume - a[1].total_volume).slice(0, 10).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Pie>
                    <RechartsTooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
              <Box>
                <Text fz="xs" c="dimmed" ta="center" mb="xs">Max Weight ({unit})</Text>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={Object.entries(data.exercise_stats).sort((a, b) => b[1].max_kg - a[1].max_kg).slice(0, 10).map(([name, s], i) => ({ name, max_weight: toDisplayUnit(s.max_kg, unit), fill: CHART_COLORS[i % CHART_COLORS.length] }))} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" /><YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12 }} />
                    <RechartsTooltip />
                    <Bar dataKey="max_weight" radius={[0, 4, 4, 0]}>
                      {Object.entries(data.exercise_stats).sort((a, b) => b[1].max_kg - a[1].max_kg).slice(0, 10).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </SimpleGrid>
          )}
        </Paper>
      )}

      {/* Muscle Workload */}
      {Object.keys(muscleGroupAvgWeekly.sets).length > 0 && (
        <Paper withBorder p="md">
          <MuscleWorkloadMap setsPerWeek={muscleGroupAvgWeekly.sets} analysisWeeks={analysisWeeks} />
        </Paper>
      )}

      {/* Monotony & Strain */}
      {data.monotony_strain && data.monotony_strain.weekly.length > 0 && (
        <Paper withBorder p="md">
          <Text fw={500} mb="sm">Foster Monotony &amp; Strain</Text>
          {viewMode === 'raw' ? (
            <Box style={{ overflowX: 'auto' }}>
              <Table fz="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Week Start</Table.Th>
                    <Table.Th ta="right">Monotony</Table.Th>
                    <Table.Th ta="right">Raw</Table.Th>
                    <Table.Th ta="right">Strain</Table.Th>
                    <Table.Th ta="right" visibleFrom="sm">Strain Index</Table.Th>
                    <Table.Th ta="right" visibleFrom="sm">Days</Table.Th>
                    <Table.Th ta="right" visibleFrom="sm">Flags</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.monotony_strain.weekly
                    .slice()
                    .sort((a, b) => a.week_start.localeCompare(b.week_start))
                    .map((row) => (
                      <Table.Tr key={row.week_start}>
                        <Table.Td fw={500}>{row.week_start}</Table.Td>
                        <Table.Td ta="right" c={row.monotony > 2 ? 'red' : 'green'}>{row.monotony.toFixed(2)}</Table.Td>
                        <Table.Td ta="right">{typeof row.monotony_raw === 'number' ? row.monotony_raw.toFixed(2) : '--'}</Table.Td>
                        <Table.Td ta="right">{row.strain.toFixed(1)}</Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">{typeof row.strain_index === 'number' ? row.strain_index.toFixed(2) : '--'}</Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">{row.nonzero_training_days ?? '--'}</Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">
                          <Group gap="xs" wrap="wrap" justify="flex-end">
                            {row.flags.length > 0 ? row.flags.map(flag => (
                              <Badge key={flag} color="yellow" variant="light" size="sm">{flag}</Badge>
                            )) : <Text span fz="sm" c="dimmed">--</Text>}
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                </Table.Tbody>
              </Table>
            </Box>
          ) : (
            <Stack gap="xs">
              {data.monotony_strain.weekly
                .slice()
                .sort((a, b) => a.week_start.localeCompare(b.week_start))
                .map((row) => (
                  <Paper key={row.week_start} p="sm" bg="var(--mantine-color-default-hover)" radius="sm">
                    <Group justify="space-between" mb={4} wrap="wrap">
                      <Text fw={700}>{row.week_start}</Text>
                      <Group gap="xs" wrap="wrap">
                        {row.flags.length > 0 ? row.flags.map(flag => (
                          <Badge key={flag} color="yellow" variant="light" size="sm">{flag}</Badge>
                        )) : <Text span fz="xs" c="dimmed">No flags</Text>}
                      </Group>
                    </Group>
                    <SimpleGrid cols={4} spacing="xs">
                      <Stack gap={0} ta="center">
                        <Text fz="xs" c="dimmed">Monotony</Text>
                        <Text fz="sm" fw={500} c={row.monotony > 2 ? 'red' : 'green'}>{row.monotony.toFixed(2)}</Text>
                      </Stack>
                      <Stack gap={0} ta="center">
                        <Text fz="xs" c="dimmed">Raw</Text>
                        <Text fz="sm" fw={500}>{typeof row.monotony_raw === 'number' ? row.monotony_raw.toFixed(2) : '--'}</Text>
                      </Stack>
                      <Stack gap={0} ta="center">
                        <Text fz="xs" c="dimmed">Strain</Text>
                        <Text fz="sm" fw={500}>{row.strain.toFixed(1)}</Text>
                      </Stack>
                      <Stack gap={0} ta="center">
                        <Text fz="xs" c="dimmed">Index / Days</Text>
                        <Text fz="sm" fw={500}>
                          {typeof row.strain_index === 'number' ? row.strain_index.toFixed(2) : '--'} / {row.nonzero_training_days ?? '--'}
                        </Text>
                      </Stack>
                    </SimpleGrid>
                  </Paper>
                ))}
            </Stack>
          )}
        </Paper>
      )}

      {/* Avg Weekly by Muscle Group */}
      {Object.keys(muscleGroupAvgWeekly.sets).length > 0 && (
        <Paper withBorder p="md">
          <Text fw={500} mb="sm">Avg Weekly by Muscle Group</Text>
          {viewMode === 'raw' ? (
            <Box style={{ overflowX: 'auto' }}>
              <Table fz="sm">
                <Table.Thead><Table.Tr><Table.Th>Muscle Group</Table.Th><Table.Th ta="right">Avg Sets/wk</Table.Th><Table.Th ta="right">Avg Vol/wk ({unit})</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {Object.entries(muscleGroupAvgWeekly.sets).sort((a, b) => (muscleGroupAvgWeekly.volume[b[0]] || 0) - (muscleGroupAvgWeekly.volume[a[0]] || 0)).map(([muscle, sets]) => (
                    <Table.Tr key={muscle}>
                      <Table.Td fw={500}>{muscle.replace(/_/g, ' ')}</Table.Td>
                      <Table.Td ta="right">{sets}</Table.Td>
                      <Table.Td ta="right">{Math.round(toDisplayUnit(muscleGroupAvgWeekly.volume[muscle] || 0, unit)).toLocaleString()}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Box>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
              <Box>
                <Text fz="xs" c="dimmed" ta="center" mb="xs">Avg Sets/wk</Text>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={Object.entries(muscleGroupAvgWeekly.sets).sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name: name.replace(/_/g, ' '), 'Avg Sets/wk': value }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
                    <YAxis /><RechartsTooltip />
                    <Bar dataKey="Avg Sets/wk" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
              <Box>
                <Text fz="xs" c="dimmed" ta="center" mb="xs">Avg Vol/wk ({unit})</Text>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={Object.entries(muscleGroupAvgWeekly.volume).sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name: name.replace(/_/g, ' '), 'Avg Vol/wk': toDisplayUnit(value, unit) }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
                    <YAxis /><RechartsTooltip />
                    <Bar dataKey="Avg Vol/wk" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </SimpleGrid>
          )}
        </Paper>
      )}
    </>
  );
}
