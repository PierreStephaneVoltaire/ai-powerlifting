import { useMemo } from 'react'
import {
  Badge,
  Box,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
} from '@mantine/core'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { TrendingUp } from 'lucide-react'
import type { PeakingTimeline as PeakingTimelineData } from '@/api/analytics'

interface PeakingTimelineProps {
  data: PeakingTimelineData | null | undefined
}

function formatShortDate(value: string): string {
  return value ? value.slice(5) : '--'
}

function formatPeakOffset(peakDeltaDays: number | null): string {
  if (peakDeltaDays === null) return 'Projected peak unavailable'
  if (peakDeltaDays === 0) return 'Projected to peak on comp day'
  const direction = peakDeltaDays > 0 ? 'early' : 'late'
  return `Projected to peak ${Math.abs(peakDeltaDays)} days ${direction}`
}

export function PeakingTimeline({ data }: PeakingTimelineProps) {
  const chartData = useMemo(() => {
    if (!data?.series?.length) return []
    return data.series.map(point => ({
      date: point.date,
      actual_tsb: point.actual_tsb,
      projected_tsb: point.projected_tsb,
    }))
  }, [data])

  const specificityPoints = useMemo(() => {
    if (!data?.specificity_points?.length) return []
    return data.specificity_points.map(point => ({
      date: point.date,
      narrow: point.narrow,
      broad: point.broad,
      weeks_to_comp: point.weeks_to_comp,
    }))
  }, [data])

  if (!data) return null

  const firstDate = chartData[0]?.date ?? data.current_date
  const lastDate = chartData[chartData.length - 1]?.date ?? data.comp_date ?? data.current_date
  const projectedPeakDate = data.peak_date ?? data.closest_peak_date ?? null

  return (
    <Paper
      withBorder
      p="md"
      style={{
        background: 'linear-gradient(180deg, var(--mantine-color-body) 0%, var(--mantine-color-gray-0) 100%)',
      }}
    >
      <Group justify="space-between" align="flex-start" mb="sm">
        <Group gap="xs">
          <TrendingUp size={18} />
          <Text fw={600}>Peaking Timeline</Text>
        </Group>
        <Badge variant="light" color={data.status_color} size="sm">
          {data.status_label}
        </Badge>
      </Group>

      {data.status === 'insufficient_data' ? (
        <Text fz="sm" c="dimmed">
          {data.reason ?? data.status_message}
        </Text>
      ) : (
        <Stack gap="md">
          <Text fz="sm" c="dimmed">
            {data.status_message}
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
            <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
              <Text fz="xs" c="dimmed">Current TSB</Text>
              <Text fz="xl" fw={700}>
                {data.current_tsb !== null ? data.current_tsb.toFixed(1) : '--'}
              </Text>
            </Stack>
            <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
              <Text fz="xs" c="dimmed">{data.peak_date ? 'Projected peak' : 'Closest projected peak'}</Text>
              <Text fz="xl" fw={700}>
                {projectedPeakDate ?? '--'}
              </Text>
              {!data.peak_date && typeof data.closest_projected_tsb === 'number' && (
                <Text fz="xs" c="dimmed">TSB {data.closest_projected_tsb.toFixed(1)}</Text>
              )}
            </Stack>
            <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
              <Text fz="xs" c="dimmed">Meet date</Text>
              <Text fz="xl" fw={700}>
                {data.comp_date ?? '--'}
              </Text>
            </Stack>
          </SimpleGrid>

          <Box style={{ width: '100%', height: 420 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="var(--mantine-color-default-border)"
                />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatShortDate}
                  minTickGap={20}
                  tick={{ fill: 'var(--mantine-color-dimmed)' }}
                  axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                  tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: 'var(--mantine-color-dimmed)' }}
                  axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                  tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 1]}
                  tickFormatter={(value) => `${Math.round(Number(value) * 100)}%`}
                  tick={{ fill: 'var(--mantine-color-dimmed)' }}
                  axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                  tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                />
                <RechartsTooltip
                  labelFormatter={(label) => `Date: ${String(label)}`}
                  formatter={(value: unknown, name: string) => [
                    typeof value === 'number' ? value.toFixed(2) : '--',
                    name,
                  ]}
                  contentStyle={{
                    backgroundColor: 'var(--mantine-color-body)',
                    border: '1px solid var(--mantine-color-default-border)',
                    color: 'var(--mantine-color-text)',
                  }}
                  labelStyle={{ color: 'var(--mantine-color-text)' }}
                  itemStyle={{ color: 'var(--mantine-color-text)' }}
                />
                <Legend />

                <ReferenceArea
                  x1={firstDate}
                  x2={lastDate}
                  yAxisId="left"
                  y1={data.peak_window.min}
                  y2={data.peak_window.max}
                  fill="var(--mantine-color-green-5)"
                  fillOpacity={0.08}
                  strokeOpacity={0}
                />

                {data.specificity_bands.map((band) => (
                  <ReferenceArea
                    key={`${band.label}-${band.start_date}-${band.end_date}`}
                    x1={band.start_date}
                    x2={band.end_date}
                    yAxisId="right"
                    y1={band.narrow.min}
                    y2={band.narrow.max}
                    fill="var(--mantine-color-blue-5)"
                    fillOpacity={0.12}
                    strokeOpacity={0}
                  />
                ))}

                {data.comp_date && (
                  <ReferenceLine
                    x={data.comp_date}
                    yAxisId="left"
                    stroke="var(--mantine-color-dimmed)"
                    strokeDasharray="4 4"
                    label={{ value: 'Comp', position: 'insideTopRight' }}
                  />
                )}

                {data.current_tsb !== null && (
                  <ReferenceDot
                    x={data.current_date}
                    y={data.current_tsb}
                    yAxisId="left"
                    r={5}
                    fill="var(--mantine-color-blue-6)"
                    stroke="var(--mantine-color-white)"
                    strokeWidth={2}
                    label={{ value: 'Now', position: 'top' }}
                  />
                )}

                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="actual_tsb"
                  name="Actual TSB"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="projected_tsb"
                  name="Projected TSB"
                  stroke="#16a34a"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                  connectNulls
                />
                <Scatter
                  yAxisId="right"
                  data={specificityPoints}
                  name="Weekly specificity"
                  dataKey="narrow"
                  fill="#f59e0b"
                  stroke="#f59e0b"
                  fillOpacity={0.8}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </Box>

          <Text fz="xs" c="dimmed">
            Green band: target TSB range (+5 to +15). Blue shaded bands: expected specificity by weeks out.
          </Text>
          {!data.peak_date && data.closest_peak_date && (
            <Text fz="xs" c="dimmed">
              Closest projected peak, not true peaking-window entry.
            </Text>
          )}
          {typeof data.future_unresolved_sets === 'number' && data.future_unresolved_sets > 0 && (
            <Text fz="xs" c="dimmed">
              {data.future_unresolved_sets} future planned sets could not be resolved into load.
            </Text>
          )}
          <Text fz="xs" c="dimmed">
            {formatPeakOffset(data.peak_delta_days)}
          </Text>
        </Stack>
      )}
    </Paper>
  )
}
