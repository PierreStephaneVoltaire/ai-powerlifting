import { useMemo } from 'react'
import { Badge, Box, Group, Paper, Progress, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { AcwrResult, WeeklyAnalysis } from '@/api/analytics'
import { ChartLabel } from '@/components/analysis/ChartLabel'

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--mantine-color-body)',
  border: '1px solid var(--mantine-color-default-border)',
  color: 'var(--mantine-color-text)',
}

const AXIS_PROPS = {
  tick: { fill: 'var(--mantine-color-dimmed)' },
  axisLine: { stroke: 'var(--mantine-color-default-border)' },
  tickLine: { stroke: 'var(--mantine-color-default-border)' },
}

const DIMENSION_COLORS: Record<string, string> = {
  axial: '#ef4444',
  neural: '#8b5cf6',
  peripheral: '#22c55e',
  systemic: '#f59e0b',
}

const DEFAULT_INOL_THRESHOLDS: Record<string, { low: number; high: number }> = {
  squat: { low: 1.6, high: 3.5 },
  bench: { low: 2.0, high: 5.0 },
  deadlift: { low: 1.0, high: 2.5 },
}

const ACWR_ZONE_META: Record<string, { color: string; hex: string; label: string }> = {
  detraining_trend: { color: 'gray', hex: '#94a3b8', label: 'Detraining trend' },
  steady_load: { color: 'green', hex: '#22c55e', label: 'Steady load' },
  rapid_increase: { color: 'yellow', hex: '#eab308', label: 'Rapid increase' },
  load_spike: { color: 'red', hex: '#ef4444', label: 'Load spike' },
  unknown: { color: 'gray', hex: '#94a3b8', label: 'Unknown' },
}

export function getAcwrZoneMeta(zone?: string | null) {
  return ACWR_ZONE_META[zone ?? 'unknown'] ?? {
    color: 'gray',
    hex: '#94a3b8',
    label: zone ? zone.replace(/_/g, ' ') : 'Unknown',
  }
}

function specificityStatusBadgeColor(status?: string) {
  if (status === 'within_expected') return 'green'
  if (status === 'below_expected') return 'yellow'
  if (status === 'above_expected') return 'orange'
  return 'gray'
}

function specificityStatusLabel(status?: string) {
  if (status === 'within_expected') return 'within expected range'
  if (status === 'below_expected') return 'below expected'
  if (status === 'above_expected') return 'above expected'
  return 'no band'
}

type InolData = NonNullable<WeeklyAnalysis['inol']>

function inolZone(value: number, bounds: { low: number; high: number }) {
  if (value < bounds.low) return { color: 'yellow', label: 'Below target' }
  if (value > bounds.high) return { color: 'orange', label: 'Above target' }
  return { color: 'green', label: 'Within target' }
}

export function InolPanel({ inol }: { inol: InolData }) {
  return (
    <Paper withBorder p="md" className="if-card">
      <Text fw={500} mb={4}>Stimulus-Adjusted INOL (Window Average)</Text>
      <ChartLabel text="Weekly INOL per lift, scaled by your stimulus coefficient." formulaId="inol" />
      <SimpleGrid cols={{ base: 1, xs: 3 }} mb="sm">
        {Object.entries(inol.avg_inol).map(([lift, fallbackAdjusted]) => {
          const detail = inol.lifts?.[lift]
          const adjustedValue = detail?.adjusted ?? fallbackAdjusted
          const raw = detail?.raw ?? inol.raw_avg_inol?.[lift]
          const coefficient = detail?.coefficient ?? inol.stimulus_coefficients?.[lift] ?? 1
          const bounds = inol.phase_adjusted_thresholds?.[lift]
          const base = inol.thresholds?.[lift] ?? DEFAULT_INOL_THRESHOLDS[lift] ?? { low: 2, high: 4 }
          const display = bounds ? { low: bounds.display_low, high: bounds.display_high } : base
          const zone = inolZone(adjustedValue, display)
          const trend = inol.trend_pressure?.[lift]
          return (
            <Stack key={lift} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${zone.color}-light)` }}>
              <Text fz="xs" c="dimmed" tt="capitalize">{lift}</Text>
              <Text fz="xl" fw={700}>{adjustedValue.toFixed(2)}</Text>
              {typeof raw === 'number' && <Text fz="xs" c="dimmed">raw {raw.toFixed(2)} x {coefficient.toFixed(2)}</Text>}
              <Text fz="xs" fw={500} c={zone.color}>target {display.low.toFixed(1)}–{display.high.toFixed(1)}</Text>
              {bounds && bounds.phase_multiplier !== 1 && (
                <Text fz="xs" c="dimmed">phase multiplier x{bounds.phase_multiplier.toFixed(2)}</Text>
              )}
              {trend && <Text fz="xs" c="dimmed">trend pressure {(trend.value * 100).toFixed(0)}%</Text>}
              {inol.ramp_up_grace?.[lift] && <Badge color="blue" variant="light" size="xs">Ramp-up grace</Badge>}
            </Stack>
          )
        })}
      </SimpleGrid>
      {inol.flags.length > 0 && (
        <Group gap="xs" wrap="wrap">
          {inol.flags.map((flag) => (
            <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
          ))}
        </Group>
      )}
    </Paper>
  )
}

export function AcwrPanel({ acwr }: { acwr: NonNullable<WeeklyAnalysis['acwr']> }) {
  const ready = !('status' in acwr) ? (acwr as AcwrResult) : null
  const rows = useMemo(
    () =>
      ready
        ? Object.entries(ready.dimensions).map(([dimension, info]) => ({
            dimension,
            ratio: info.value,
            acute: info.acute ?? null,
            chronic: info.chronic ?? null,
            zone: info.zone,
            label: info.label ?? getAcwrZoneMeta(info.zone).label,
            weight: ready.weights_used?.[dimension as keyof typeof ready.weights_used] ?? null,
          }))
        : [],
    [ready],
  )

  if (!ready) {
    return (
      <Paper withBorder p="md" className="if-card">
        <Text fw={500} mb={4}>EWMA ACWR (daily workload ratio)</Text>
        <Text fz="sm" c="dimmed">{'reason' in acwr ? acwr.reason : 'Not enough data yet. Keep logging sessions.'}</Text>
      </Paper>
    )
  }

  const composite = getAcwrZoneMeta(ready.composite_zone)
  const chartRows = rows.filter((row) => row.ratio !== null)
  const missing = rows.filter((row) => row.ratio === null).map((row) => row.dimension)

  return (
    <Paper withBorder p="md" className="if-card">
      <Group justify="space-between" mb={4} align="flex-start">
        <Text fw={500}>EWMA ACWR (daily workload ratio)</Text>
        <Badge color={composite.color} variant="light">
          Composite {ready.composite?.toFixed(2) ?? 'N/A'}
          <Text span visibleFrom="sm"> ({ready.composite_label ?? composite.label})</Text>
        </Badge>
      </Group>
      <ChartLabel text="Acute load divided by chronic load, per dimension." formulaId="acwr" />
      {chartRows.length > 0 && (
        <Box style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartRows}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--mantine-color-default-border)" />
              <XAxis dataKey="dimension" {...AXIS_PROPS} />
              <YAxis domain={[0, (max: number) => Math.max(2, Math.ceil(max * 10) / 10)]} {...AXIS_PROPS} />
              <ReferenceArea y1={0.8} y2={1.3} fill="var(--mantine-color-green-5)" fillOpacity={0.12} strokeOpacity={0} label={{ value: '0.8–1.3 normal', position: 'insideTopRight', fill: 'var(--mantine-color-dimmed)', fontSize: 11 }} />
              <ReferenceLine y={1} stroke="var(--mantine-color-dimmed)" strokeDasharray="4 4" />
              <RechartsTooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value: unknown, _name: string, item: { payload?: { acute: number | null; chronic: number | null; label: string } }) => [
                  `${typeof value === 'number' ? value.toFixed(2) : '--'} (acute ${item.payload?.acute?.toFixed(1) ?? '--'} / chronic ${item.payload?.chronic?.toFixed(1) ?? '--'}) ${item.payload?.label ?? ''}`,
                  'ACWR',
                ]}
              />
              <Bar dataKey="ratio" name="ACWR" radius={[4, 4, 0, 0]}>
                {chartRows.map((row) => (
                  <Cell key={row.dimension} fill={getAcwrZoneMeta(row.zone).hex} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md" mt="sm">
        {rows.map((row) => {
          const zone = getAcwrZoneMeta(row.zone)
          return (
            <Stack key={row.dimension} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${zone.color}-light)` }}>
              <Text fz="xs" tt="capitalize">{row.dimension}</Text>
              <Text fz="xl" fw={700}>{row.ratio?.toFixed(2) ?? '--'}</Text>
              <Text fz="xs">{row.label}</Text>
              <Text fz="xs" c="dimmed">acute {row.acute?.toFixed(1) ?? '--'} / chronic {row.chronic?.toFixed(1) ?? '--'}</Text>
              {row.weight !== null && <Text fz="xs" c="dimmed">weight {(row.weight * 100).toFixed(0)}%</Text>}
            </Stack>
          )
        })}
      </SimpleGrid>
      {missing.length > 0 && (
        <Text fz="xs" c="dimmed" mt="xs">
          No ratio yet for {missing.join(', ')}; excluded from the composite.
        </Text>
      )}
    </Paper>
  )
}

export function SpecificityPanel({
  specificity,
  target,
}: {
  specificity: NonNullable<WeeklyAnalysis['specificity_ratio']>
  target?: WeeklyAnalysis['specificity_target_competition']
}) {
  const band = specificity.expected_band
  const secondary = specificity.secondary_sets ?? 0
  const weighted = specificity.weighted_sets
  return (
    <Paper withBorder p="md" className="if-card">
      <Group justify="space-between" align="flex-start" mb={4}>
        <Text fw={500}>Specificity Ratio</Text>
        {band ? (
          <Group gap="xs" wrap="wrap" justify="flex-end">
            <Badge variant="light" color={specificityStatusBadgeColor(specificity.narrow_status)}>
              Narrow {specificityStatusLabel(specificity.narrow_status)}
            </Badge>
            <Badge variant="light" color={specificityStatusBadgeColor(specificity.broad_status)}>
              Broad {specificityStatusLabel(specificity.broad_status)}
            </Badge>
          </Group>
        ) : (
          <Badge variant="light" color="gray">No upcoming comp band</Badge>
        )}
      </Group>
      <ChartLabel text="Share of sets that are competition-specific." formulaId="specificity_ratio" />
      {target && (
        <Text fz="xs" c="dimmed" mb="sm">
          Target: {target.name ?? 'Upcoming meet'}
          {target.date ? ` (${target.date})` : ''}
          {target.selection_reason ? ` • ${String(target.selection_reason).replace(/_/g, ' ')}` : ''}
        </Text>
      )}
      <SimpleGrid cols={2} spacing="md">
        <Stack gap="xs">
          <Text fz="xs" c="dimmed">Narrow (competition lifts only)</Text>
          <Progress value={Math.min(specificity.narrow * 100, 100)} />
          <Text fz="sm" fw={500}>{(specificity.narrow * 100).toFixed(1)}%{band && <Text span fz="xs" c="dimmed"> expected {(band.narrow.min * 100).toFixed(0)}–{(band.narrow.max * 100).toFixed(0)}%</Text>}</Text>
        </Stack>
        <Stack gap="xs">
          <Text fz="xs" c="dimmed">Broad (transfer-weighted)</Text>
          <Progress value={Math.min(specificity.broad * 100, 100)} color="blue" />
          <Text fz="sm" fw={500}>{(specificity.broad * 100).toFixed(1)}%{band && <Text span fz="xs" c="dimmed"> expected {(band.broad.min * 100).toFixed(0)}–{(band.broad.max * 100).toFixed(0)}%</Text>}</Text>
        </Stack>
      </SimpleGrid>
      <Text fz="xs" c="dimmed" mt="sm">
        {specificity.sbd_sets} competition sets + {secondary.toFixed(1)} accessory sets
        {typeof weighted === 'number' ? ` (transfer-weighted ${weighted.toFixed(1)})` : ''} of {specificity.total_sets} total
      </Text>
      {specificity.flags && specificity.flags.length > 0 && (
        <Group gap="xs" wrap="wrap" mt="sm">
          {specificity.flags.map((flag) => (
            <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
          ))}
        </Group>
      )}
    </Paper>
  )
}

export function FatigueDimensionsPanel({ dimensions }: { dimensions: NonNullable<WeeklyAnalysis['fatigue_dimensions']> }) {
  const rows = useMemo(() => {
    const source = dimensions.normalized ?? dimensions.weekly
    return Object.entries(source)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([week, ratios]) => ({
        week: `W${week}`,
        ...ratios,
        raw: dimensions.weekly[week],
      }))
  }, [dimensions])
  const hasNormalized = Boolean(dimensions.normalized)

  return (
    <Paper withBorder p="md" className="if-card">
      <Text fw={500} mb={4}>Fatigue Dimensions (Weekly)</Text>
      <ChartLabel text="Weekly load by recovery dimension, compared with your typical week." formulaId="fatigue_model" />
      <Box style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ right: 72 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--mantine-color-default-border)" />
            <XAxis dataKey="week" {...AXIS_PROPS} />
            <YAxis {...AXIS_PROPS} domain={[0, (max: number) => Math.max(1.5, Math.ceil(max * 10) / 10)]} />
            {hasNormalized && (
              <ReferenceLine y={1} stroke="var(--mantine-color-dimmed)" strokeDasharray="4 4" label={{ value: '1.0 = typical week', position: 'insideTopLeft', fill: 'var(--mantine-color-dimmed)', fontSize: 11 }} />
            )}
            <RechartsTooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: unknown, name: string, item: { payload?: { raw?: Record<string, number> } }) => {
                const raw = item.payload?.raw?.[name]
                return [
                  `${typeof value === 'number' ? value.toFixed(2) : '--'}${hasNormalized ? 'x' : ''}${typeof raw === 'number' && hasNormalized ? ` (raw ${raw.toFixed(1)})` : ''}`,
                  name,
                ]
              }}
            />
            <Legend />
            {(['axial', 'neural', 'peripheral', 'systemic'] as const).map((dimension) => (
              <Line
                key={dimension}
                type="monotone"
                dataKey={dimension}
                name={dimension}
                stroke={DIMENSION_COLORS[dimension]}
                strokeWidth={2}
                dot={{ r: 3 }}
                label={(props: { x?: number; y?: number; value?: number; index?: number }) =>
                  props.index === rows.length - 1 && typeof props.value === 'number' && typeof props.x === 'number' && typeof props.y === 'number' ? (
                    <text key={dimension} x={props.x + 8} y={props.y + 4} fontSize={11} fill={DIMENSION_COLORS[dimension]}>
                      {`${dimension} ${props.value.toFixed(2)}`}
                    </text>
                  ) : <g key={`${dimension}-${props.index}`} />
                }
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Box>
      <Box style={{ overflowX: 'auto' }} mt="sm">
        <Table fz="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Week</Table.Th>
              <Table.Th ta="right">Axial</Table.Th>
              <Table.Th ta="right">Neural</Table.Th>
              <Table.Th ta="right">Peripheral</Table.Th>
              <Table.Th ta="right">Systemic</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.slice(-8).map((row) => (
              <Table.Tr key={row.week}>
                <Table.Td fw={500}>{row.week}</Table.Td>
                {(['axial', 'neural', 'peripheral', 'systemic'] as const).map((dimension) => (
                  <Table.Td key={dimension} ta="right">
                    {row[dimension].toFixed(2)}{hasNormalized ? 'x' : ''}
                    {hasNormalized && row.raw && <Text span fz="xs" c="dimmed"> ({row.raw[dimension].toFixed(1)})</Text>}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Box>
    </Paper>
  )
}
