import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Brain,
  CheckCircle,
  Database,
  Download,
  Eye,
  GitCompare,
  History,
  RefreshCw,
  Save,
  Trophy,
} from 'lucide-react'
import {
  Badge,
  Box,
  Button,
  Center,
  Checkbox,
  Group,
  Loader,
  TextInput,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  fetchAiBlockComparison,
  fetchBlockAnalysis,
  fetchBlockProgramEvaluation,
  fetchProgramBlocks,
  blockAnalysisExportUrl,
  updateBlockStartMaxes,
  type AiBlockComparisonResult,
  type BlockAnalysisBundle,
  type BlockComparisonResult,
  type DataQualityFlag,
  type ProgramEvaluationReport,
  type ProgramBlockIndexEntry,
} from '@/api/analytics'
import { toDisplayUnit } from '@/utils/units'
import { BlockWeeklySurface } from '@/components/analysis/BlockWeeklySurface'
import type { Program } from '@powerlifting/types'

type WeightUnit = 'kg' | 'lb'

function flagColor(flag: DataQualityFlag): string {
  if (flag.severity === 'critical') return 'red'
  if (flag.severity === 'warning') return 'yellow'
  return 'gray'
}

function cacheBadge(block: ProgramBlockIndexEntry) {
  if (block.cacheStatus?.cached) {
    return <Badge color="green" variant="light" size="sm">Cached</Badge>
  }
  return <Badge color="gray" variant="light" size="sm">Generate</Badge>
}

function kg(value: number | null | undefined, unit: WeightUnit): string {
  return typeof value === 'number' ? `${toDisplayUnit(value, unit).toFixed(1)} ${unit}` : '--'
}

function percent(value: number | null | undefined, multiplier = 1): string {
  return typeof value === 'number' ? `${(value * multiplier).toFixed(1)}%` : '--'
}

function metric(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' ? value.toFixed(digits) : '--'
}

function sortedPastBlocks(blocks: ProgramBlockIndexEntry[]): ProgramBlockIndexEntry[] {
  return blocks
    .filter((block) => !block.isCurrent)
    .sort((a, b) => b.endDate.localeCompare(a.endDate))
}

function QualityBadges({ flags }: { flags: DataQualityFlag[] }) {
  if (!flags.length) {
    return <Badge color="green" variant="light" size="sm">Complete</Badge>
  }
  return (
    <Group gap={6} wrap="wrap">
      {flags.map((flag) => (
        <Tooltip key={flag.code} label={flag.code} withArrow>
          <Badge color={flagColor(flag)} variant="light" size="sm">{flag.label}</Badge>
        </Tooltip>
      ))}
    </Group>
  )
}

function compactText(value: unknown): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return [
      record.block,
      record.lift,
      record.finding,
      record.change,
      record.experiment,
      record.reason,
      record.why,
      record.evidence,
      record.tradeoff,
      record.risk,
      record.success_metric,
      record.confidence ? `Confidence: ${record.confidence}` : null,
    ].filter(Boolean).join(' - ')
  }
  return String(value ?? '')
}

function TextList({ items, empty = 'No findings yet.' }: { items: unknown[] | undefined; empty?: string }) {
  if (!items?.length) return <Text fz="sm" c="dimmed">{empty}</Text>
  return (
    <Stack gap={6}>
      {items.map((item, index) => (
        <Text key={index} fz="sm">{compactText(item)}</Text>
      ))}
    </Stack>
  )
}

function ProgramEvaluationSection({
  report,
  loading,
  error,
  onRefresh,
}: {
  report: ProgramEvaluationReport | null
  loading: boolean
  error: string | null
  onRefresh: () => void
}) {
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <Brain size={18} />
          <Text fw={500}>Program Analysis</Text>
          {report?.cached && <Badge color="green" variant="light" size="sm">Cached</Badge>}
          {report?.cache_miss && <Badge color="gray" variant="light" size="sm">Not generated</Badge>}
          {report?.insufficient_data && <Badge color="yellow" variant="light" size="sm">Limited data</Badge>}
        </Group>
        <Button size="xs" variant="subtle" leftSection={<RefreshCw size={14} />} loading={loading} onClick={onRefresh}>
          {report?.cache_miss ? 'Generate' : 'Refresh'}
        </Button>
      </Group>
      {error && <Text c="red" fz="sm">{error}</Text>}
      {loading && !report ? (
        <Center mih={80}><Loader size="sm" /></Center>
      ) : report ? (
        <Stack gap="sm">
          <Text fz="sm">{report.summary || report.insufficient_data_reason || 'No program analysis summary returned.'}</Text>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Stack gap={4}>
              <Text fw={500} fz="sm">Working</Text>
              <TextList items={report.what_is_working} />
            </Stack>
            <Stack gap={4}>
              <Text fw={500} fz="sm">Not Working</Text>
              <TextList items={report.what_is_not_working} />
            </Stack>
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Stack gap={4}>
              <Text fw={500} fz="sm">Adjustments</Text>
              <TextList items={report.small_changes} />
            </Stack>
            <Stack gap={4}>
              <Text fw={500} fz="sm">Monitoring</Text>
              <TextList items={report.monitoring_focus} />
            </Stack>
          </SimpleGrid>
          {report.conclusion && <Text fz="sm" c="dimmed">{report.conclusion}</Text>}
        </Stack>
      ) : (
        <Text fz="sm" c="dimmed">Program analysis has not been generated for this block.</Text>
      )}
    </Paper>
  )
}

function BlockAnalysisDetails({
  bundle,
  unit,
  program,
  version,
  sex,
  onBundleUpdated,
}: {
  bundle: BlockAnalysisBundle
  unit: WeightUnit
  program: Program | null
  version: string
  sex: 'male' | 'female'
  onBundleUpdated: (bundle: BlockAnalysisBundle) => void
}) {
  const outcome = bundle.historical.competitionOutcome
  const summary = bundle.historical.analyticsSummary
  const [startMaxes, setStartMaxes] = useState({
    squat_kg: bundle.historical.manualStartMaxes?.squat_kg ?? bundle.historical.startStrength.squat,
    bench_kg: bundle.historical.manualStartMaxes?.bench_kg ?? bundle.historical.startStrength.bench,
    deadlift_kg: bundle.historical.manualStartMaxes?.deadlift_kg ?? bundle.historical.startStrength.deadlift,
  })
  const [savingStartMaxes, setSavingStartMaxes] = useState(false)
  const [startMaxError, setStartMaxError] = useState<string | null>(null)
  const [programEvaluation, setProgramEvaluation] = useState<ProgramEvaluationReport | null>(null)
  const [programEvaluationLoading, setProgramEvaluationLoading] = useState(false)
  const [programEvaluationError, setProgramEvaluationError] = useState<string | null>(null)

  useEffect(() => {
    setStartMaxes({
      squat_kg: bundle.historical.manualStartMaxes?.squat_kg ?? bundle.historical.startStrength.squat,
      bench_kg: bundle.historical.manualStartMaxes?.bench_kg ?? bundle.historical.startStrength.bench,
      deadlift_kg: bundle.historical.manualStartMaxes?.deadlift_kg ?? bundle.historical.startStrength.deadlift,
    })
    setStartMaxError(null)
  }, [
    bundle.block.blockKey,
    bundle.historical.manualStartMaxes,
    bundle.historical.startStrength.squat,
    bundle.historical.startStrength.bench,
    bundle.historical.startStrength.deadlift,
  ])

  const loadProgramEvaluation = (refresh = false, cacheOnly = false) => {
    setProgramEvaluationLoading(true)
    setProgramEvaluationError(null)
    fetchBlockProgramEvaluation(bundle.block.blockKey, refresh, cacheOnly)
      .then(setProgramEvaluation)
      .catch((err) => setProgramEvaluationError(err.message))
      .finally(() => setProgramEvaluationLoading(false))
  }

  useEffect(() => {
    setProgramEvaluation(null)
    loadProgramEvaluation(false, true)
  }, [bundle.block.blockKey])

  const saveStartMaxes = async () => {
    setSavingStartMaxes(true)
    setStartMaxError(null)
    try {
      await updateBlockStartMaxes(bundle.block.blockKey, startMaxes)
      const refreshed = await fetchBlockAnalysis(bundle.block.blockKey, true)
      onBundleUpdated(refreshed)
    } catch (err) {
      setStartMaxError(err instanceof Error ? err.message : String(err))
    } finally {
      setSavingStartMaxes(false)
    }
  }

  return (
    <Stack gap="md">
      <Group justify="flex-end" wrap="wrap">
        <Button
          component="a"
          href={blockAnalysisExportUrl(bundle.block.blockKey, 'xlsx')}
          download
          size="sm"
          leftSection={<Download size={16} />}
        >
          Export Excel
        </Button>
        <Button
          component="a"
          href={blockAnalysisExportUrl(bundle.block.blockKey, 'markdown')}
          download
          size="sm"
          variant="light"
          leftSection={<Download size={16} />}
        >
          Export Markdown
        </Button>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }}>
        <Paper withBorder p="md">
          <Group gap="xs" mb="xs">
            <History size={18} />
            <Text fw={500}>Block Window</Text>
          </Group>
          <Text fz="xl" fw={700}>{bundle.block.weekCount} weeks</Text>
          <Text fz="sm" c="dimmed">{bundle.block.startDate} to {bundle.block.endDate}</Text>
          <Text fz="xs" c="dimmed">{bundle.block.completedSessions}/{bundle.block.totalSessions} sessions completed</Text>
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="xs">
            <CheckCircle size={18} />
            <Text fw={500}>Compliance</Text>
          </Group>
          <Text fz="xl" fw={700}>{percent(summary.compliancePct)}</Text>
          <Text fz="sm" c="dimmed">{summary.sessionsAnalyzed} sessions analyzed</Text>
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="xs">
            <BarChart3 size={18} />
            <Text fw={500}>Load</Text>
          </Group>
          <Text fz="xl" fw={700}>{summary.totalVolumeKg.toLocaleString()} kg</Text>
          <Text fz="sm" c="dimmed">Total completed volume</Text>
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="xs">
            <AlertTriangle size={18} />
            <Text fw={500}>Fatigue</Text>
          </Group>
          <Text fz="xl" fw={700}>{percent(summary.fatigueIndex, 100)}</Text>
          <Text fz="sm" c="dimmed">Current state at block end</Text>
        </Paper>
      </SimpleGrid>

      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm" align="flex-start">
          <Stack gap={2}>
            <Group gap="xs">
              <Save size={18} />
              <Text fw={500}>Block Start Maxes</Text>
              <Badge color={bundle.historical.startMaxesSource === 'manual' ? 'blue' : 'gray'} variant="light" size="sm">
                {bundle.historical.startMaxesSource === 'manual' ? 'Manual' : 'Estimated'}
              </Badge>
            </Group>
            <Text fz="xs" c="dimmed">Set the athlete's maxes at the beginning of this block so deltas are not inferred from early sessions.</Text>
          </Stack>
          <Button size="xs" leftSection={<Save size={14} />} loading={savingStartMaxes} onClick={saveStartMaxes}>
            Save
          </Button>
        </Group>
        {startMaxError && <Text c="red" fz="sm" mb="sm">{startMaxError}</Text>}
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          {([
            ['squat_kg', 'Squat'],
            ['bench_kg', 'Bench'],
            ['deadlift_kg', 'Deadlift'],
          ] as const).map(([key, label]) => (
            <TextInput
              key={key}
              type="number"
              label={label}
              value={startMaxes[key] ?? ''}
              rightSection={<Text size="xs" c="dimmed" pr="xs">kg</Text>}
              rightSectionWidth={40}
              step={0.5}
              onChange={(e) => {
                const value = e.currentTarget.value
                setStartMaxes((current) => ({
                  ...current,
                  [key]: value !== '' && !isNaN(Number(value)) ? Number(value) : null,
                }))
              }}
            />
          ))}
        </SimpleGrid>
      </Paper>

      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm">
            <BarChart3 size={18} />
            <Text fw={500}>Strength Start / End</Text>
          </Group>
          <Table fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Lift</Table.Th>
                <Table.Th ta="right">Start</Table.Th>
                <Table.Th ta="right">End</Table.Th>
                <Table.Th ta="right">Delta</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(['squat', 'bench', 'deadlift', 'total'] as const).map((lift) => (
                <Table.Tr key={lift}>
                  <Table.Td tt="capitalize">{lift === 'total' ? 'Total' : lift}</Table.Td>
                  <Table.Td ta="right">{kg(bundle.historical.startStrength[lift], unit)}</Table.Td>
                  <Table.Td ta="right">{kg(bundle.historical.endStrength[lift], unit)}</Table.Td>
                  <Table.Td ta="right">{kg(bundle.historical.strengthDelta[lift], unit)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="sm">
            <Trophy size={18} />
            <Text fw={500}>Competition Outcome</Text>
            {bundle.block.trainingOnly && <Badge color="gray" variant="light" size="sm">Training only</Badge>}
          </Group>
          {outcome ? (
            <Stack gap="sm">
              <Group justify="space-between">
                <Stack gap={0}>
                  <Text fw={500}>{outcome.competitionName}</Text>
                  <Text fz="sm" c="dimmed">{outcome.competitionDate}</Text>
                </Stack>
                <Stack gap={0} ta="right">
                  <Text fw={700}>{kg(outcome.results?.total_kg, unit)}</Text>
                  <Text fz="xs" c="dimmed">Actual total</Text>
                </Stack>
              </Group>
              <SimpleGrid cols={3}>
                <Stack gap={0}>
                  <Text fz="xs" c="dimmed">DOTS</Text>
                  <Text fw={700}>{metric(outcome.dots, 2)}</Text>
                </Stack>
                <Stack gap={0}>
                  <Text fz="xs" c="dimmed">IPF GL</Text>
                  <Text fw={700}>{metric(outcome.ipfGl, 2)}</Text>
                </Stack>
                <Stack gap={0}>
                  <Text fz="xs" c="dimmed">Bodyweight</Text>
                  <Text fw={700}>{kg(outcome.bodyweightKg, unit)}</Text>
                </Stack>
              </SimpleGrid>
              {outcome.projectionAccuracy && (
                <Table fz="xs">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Projection</Table.Th>
                      <Table.Th ta="right">Actual</Table.Th>
                      <Table.Th ta="right">Projected</Table.Th>
                      <Table.Th ta="right">Delta</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(['squat_kg', 'bench_kg', 'deadlift_kg', 'total_kg'] as const).map((key) => {
                      const item = outcome.projectionAccuracy?.[key]
                      if (!item) return null
                      const label = key.replace('_kg', '').replace('deadlift', 'deadlift')
                      return (
                        <Table.Tr key={key}>
                          <Table.Td tt="capitalize">{label === 'total' ? 'Total' : label}</Table.Td>
                          <Table.Td ta="right">{kg(item.actualKg, unit)}</Table.Td>
                          <Table.Td ta="right">{kg(item.projectedKg, unit)}</Table.Td>
                          <Table.Td ta="right">{kg(item.deltaKg, unit)}</Table.Td>
                        </Table.Tr>
                      )
                    })}
                  </Table.Tbody>
                </Table>
              )}
            </Stack>
          ) : (
            <Text fz="sm" c="dimmed">No completed competition maps to this block.</Text>
          )}
        </Paper>
      </SimpleGrid>

      <Paper withBorder p="md">
        <Group gap="xs" mb="sm">
          <Database size={18} />
          <Text fw={500}>Data Quality</Text>
        </Group>
        <QualityBadges flags={bundle.historical.missingData} />
      </Paper>

      <ProgramEvaluationSection
        report={programEvaluation}
        loading={programEvaluationLoading}
        error={programEvaluationError}
        onRefresh={() => loadProgramEvaluation(true)}
      />

      <BlockWeeklySurface
        program={program}
        bundle={bundle}
        unit={unit}
        sex={sex}
        version={version}
      />
    </Stack>
  )
}

export function PastBlocksPanel({ unit }: { unit: WeightUnit }) {
  const { program, version } = useProgramStore()
  const { sex } = useSettingsStore()
  const [blocks, setBlocks] = useState<ProgramBlockIndexEntry[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [bundle, setBundle] = useState<BlockAnalysisBundle | null>(null)
  const [loadingBlocks, setLoadingBlocks] = useState(false)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pastBlocks = useMemo(() => sortedPastBlocks(blocks), [blocks])

  useEffect(() => {
    setLoadingBlocks(true)
    setError(null)
    fetchProgramBlocks()
      .then((result) => {
        setBlocks(result)
        const first = sortedPastBlocks(result)[0]
        if (first) setSelectedKey((current) => current ?? first.blockKey)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoadingBlocks(false))
  }, [])

  const loadAnalysis = (blockKey: string, refresh = false) => {
    setSelectedKey(blockKey)
    setLoadingAnalysis(true)
    setError(null)
    fetchBlockAnalysis(blockKey, refresh)
      .then(setBundle)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingAnalysis(false))
  }

  if (loadingBlocks) {
    return <Center mih="20vh"><Loader /></Center>
  }

  if (!pastBlocks.length) {
    return (
      <Paper withBorder p="lg">
        <Text fw={500}>No past blocks found</Text>
        <Text fz="sm" c="dimmed">Past blocks are discovered from non-current values in session.block on the current program.</Text>
      </Paper>
    )
  }

  return (
    <Stack gap="md">
      {error && (
        <Paper withBorder p="md" style={{ borderColor: 'var(--mantine-color-red-4)' }}>
          <Text c="red">{error}</Text>
        </Paper>
      )}

      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <History size={18} />
            <Title order={3} fz="lg">Past Blocks</Title>
          </Group>
          <Badge variant="light">{pastBlocks.length} blocks</Badge>
        </Group>
        <Box style={{ overflowX: 'auto' }}>
          <Table fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Block</Table.Th>
                <Table.Th>Date Range</Table.Th>
                <Table.Th visibleFrom="sm">Sessions</Table.Th>
                <Table.Th visibleFrom="sm">Competition</Table.Th>
                <Table.Th visibleFrom="sm">Quality</Table.Th>
                <Table.Th visibleFrom="sm">Cache</Table.Th>
                <Table.Th ta="right">Actions</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {pastBlocks.map((block) => (
                <Table.Tr key={block.blockKey} bg={selectedKey === block.blockKey ? 'var(--mantine-color-default-hover)' : undefined}>
                  <Table.Td>
                    <Text fw={500}>{block.label}</Text>
                    <Text fz="xs" c="dimmed">W{block.weekStart}-{block.weekEnd}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text fz="sm">{block.startDate}</Text>
                    <Text fz="xs" c="dimmed">to {block.endDate}</Text>
                  </Table.Td>
                  <Table.Td visibleFrom="sm">{block.completedSessions}/{block.totalSessions}</Table.Td>
                  <Table.Td visibleFrom="sm">
                    {block.linkedCompetition ? (
                      <Stack gap={0}>
                        <Text fz="sm">{block.linkedCompetition.name}</Text>
                        <Text fz="xs" c="dimmed">{block.linkedCompetition.date}</Text>
                      </Stack>
                    ) : (
                      <Badge color="gray" variant="light" size="sm">Training only</Badge>
                    )}
                  </Table.Td>
                  <Table.Td visibleFrom="sm"><QualityBadges flags={block.dataQualityFlags} /></Table.Td>
                  <Table.Td visibleFrom="sm">{cacheBadge(block)}</Table.Td>
                  <Table.Td ta="right">
                    <Group gap={6} justify="flex-end" wrap="nowrap">
                      <Button size="xs" variant="light" leftSection={<Eye size={14} />} onClick={() => loadAnalysis(block.blockKey, false)}>
                        View
                      </Button>
                      <Button size="xs" variant="subtle" leftSection={<RefreshCw size={14} />} onClick={() => loadAnalysis(block.blockKey, true)}>
                        Refresh
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Box>
      </Paper>

      {loadingAnalysis && <Center mih="12vh"><Loader size="sm" /></Center>}
      {bundle && !loadingAnalysis && (
        <BlockAnalysisDetails
          bundle={bundle}
          unit={unit}
          program={program}
          version={version}
          sex={sex}
          onBundleUpdated={setBundle}
        />
      )}
    </Stack>
  )
}

const TREND_COLORS = ['#2563eb', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#dc2626']

function trendBlockLines(comparison: BlockComparisonResult) {
  const labels = new Map<string, string>()
  for (const point of comparison.trendSeries ?? []) {
    labels.set(point.blockKey, point.label)
  }
  return [...labels.entries()].map(([blockKey, label], index) => ({
    blockKey,
    label,
    color: TREND_COLORS[index % TREND_COLORS.length],
  }))
}

function trendChartData(
  comparison: BlockComparisonResult,
  metricKey: 'e1rmTotalKg' | 'estimatedDots' | 'volumeKg' | 'trainingDays',
  unit: WeightUnit,
) {
  const weeks = new Map<number, Record<string, number | string | null>>()
  for (const point of comparison.trendSeries ?? []) {
    const row = weeks.get(point.weekNumber) ?? { week: `W${point.weekNumber}`, weekNumber: point.weekNumber }
    const value = point[metricKey]
    row[point.blockKey] = typeof value === 'number'
      ? (metricKey === 'e1rmTotalKg' || metricKey === 'volumeKg' ? Number(toDisplayUnit(value, unit).toFixed(1)) : value)
      : null
    weeks.set(point.weekNumber, row)
  }
  return [...weeks.values()].sort((a, b) => Number(a.weekNumber) - Number(b.weekNumber))
}

function AiReportSection({ comparison }: { comparison: AiBlockComparisonResult }) {
  const report = comparison.report
  const sections: Array<[string, unknown[] | undefined]> = [
    ['Similarities', report.similarities],
    ['Differences', report.differences],
    ['What Worked', report.what_works],
    ['What Did Not Work', report.what_does_not_work],
    ['Lift Specific', report.lift_specific_insights],
    ['Exercise ROI', report.multi_block_exercise_roi],
    ['Cross-Block Correlations', report.cross_block_correlations],
    ['Pattern Detection', report.pattern_detections],
    ['Volume Dose Response', report.volume_dose_response],
    ['Bodyweight Relationship', report.bodyweight_relationships],
    ['Training Days', report.training_day_frequency],
    ['Best Value Blocks', report.best_value_blocks],
    ['Projection Accuracy', report.projection_accuracy],
    ['Progress Dropoffs', report.progress_dropoff_points],
    ['Fatigue Patterns', report.fatigue_patterns],
    ['Data Limits', report.data_limits],
  ]

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <Brain size={18} />
          <Text fw={500}>AI Lifetime Analysis</Text>
          {comparison.cached && <Badge color="green" variant="light" size="sm">Saved</Badge>}
          {report.insufficient_data && <Badge color="yellow" variant="light" size="sm">Limited data</Badge>}
        </Group>
        <Text fz="xs" c="dimmed">{comparison.selectedBlockKeys.length} blocks</Text>
      </Group>
      <Stack gap="md">
        <Text fz="sm">{report.overall_summary || report.insufficient_data_reason || 'No AI summary returned.'}</Text>
        <SimpleGrid cols={{ base: 1, lg: 2 }}>
          {sections.map(([title, items]) => (
            <Paper key={title} withBorder p="sm">
              <Text fw={500} fz="sm">{title}</Text>
              <TextList items={items} />
            </Paper>
          ))}
        </SimpleGrid>
      </Stack>
    </Paper>
  )
}

function confidenceColor(confidence: string): string {
  if (confidence === 'high') return 'green'
  if (confidence === 'medium') return 'blue'
  return 'yellow'
}

function directionColor(direction: string): string {
  if (direction === 'positive') return 'green'
  if (direction === 'negative') return 'red'
  return 'gray'
}

function ConsolidatedRoiSection({ comparison, unit }: { comparison: BlockComparisonResult; unit: WeightUnit }) {
  const exerciseRoi = comparison.exerciseRoi ?? []
  const patterns = comparison.patternSignals ?? []
  const findings = comparison.correlationFindings ?? []

  return (
    <Stack gap="md">
      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm" align="flex-start">
          <Stack gap={2}>
            <Group gap="xs">
              <GitCompare size={18} />
              <Text fw={500}>Exercise ROI Source Detail</Text>
            </Group>
            <Text fz="xs" c="dimmed">
              Exercise volume and correlation details from the selected source analyses. Current block is scoped to completed block-to-date data.
            </Text>
          </Stack>
          <Badge variant="light">{comparison.rows.length} source blocks</Badge>
        </Group>

        {comparison.rows.length < 2 ? (
          <Text fz="sm" c="dimmed">At least two source block analyses are needed for lifetime exercise ROI.</Text>
        ) : exerciseRoi.length ? (
          <Box style={{ overflowX: 'auto' }}>
            <Table fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Exercise</Table.Th>
                  <Table.Th ta="right">Blocks</Table.Th>
                  <Table.Th ta="right">Sets</Table.Th>
                  <Table.Th ta="right">Volume</Table.Th>
                  <Table.Th>Signals</Table.Th>
                  <Table.Th>Pattern</Table.Th>
                  <Table.Th>Confidence</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {exerciseRoi.map((row) => (
                  <Table.Tr key={row.exercise}>
                    <Table.Td>
                      <Text fw={500}>{row.exercise}</Text>
                      <Text fz="xs" c="dimmed">
                        {row.blocks.map((block) => `${block.label}: ${block.sets} sets`).join(' · ')}
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">{row.blockCount}</Table.Td>
                    <Table.Td ta="right">{row.totalSets}</Table.Td>
                    <Table.Td ta="right">{kg(row.totalVolumeKg, unit)}</Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        <Badge color="green" variant="light" size="xs">+{row.positiveSignals}</Badge>
                        <Badge color="red" variant="light" size="xs">-{row.negativeSignals}</Badge>
                        <Badge color="gray" variant="light" size="xs">?{row.unclearSignals}</Badge>
                      </Group>
                      {row.correlatedLifts.length > 0 && (
                        <Text fz="xs" c="dimmed">{row.correlatedLifts.join(', ')}</Text>
                      )}
                    </Table.Td>
                    <Table.Td maw={420}>
                      <Text fz="sm">{row.summary}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={confidenceColor(row.confidence)} variant="light" size="sm">{row.confidence}</Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Box>
        ) : (
          <Text fz="sm" c="dimmed">No repeated exercise ROI signals were found in the selected source blocks.</Text>
        )}
      </Paper>

      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm">
            <Brain size={18} />
            <Text fw={500}>Pattern Detection</Text>
          </Group>
          <Stack gap="sm">
            {patterns.length ? patterns.map((pattern, index) => (
              <Stack key={`${pattern.kind}-${index}`} gap={2}>
                <Group gap={6}>
                  <Badge color="gray" variant="light" size="xs">{pattern.kind.replace('_', ' ')}</Badge>
                  <Badge color={confidenceColor(pattern.confidence)} variant="light" size="xs">{pattern.confidence}</Badge>
                </Group>
                <Text fz="sm" fw={500}>{pattern.finding}</Text>
                <Text fz="xs" c="dimmed">{pattern.evidence}</Text>
              </Stack>
            )) : (
              <Text fz="sm" c="dimmed">No multi-block patterns detected yet.</Text>
            )}
          </Stack>
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="sm">
            <Database size={18} />
            <Text fw={500}>Correlation Findings</Text>
          </Group>
          <Stack gap="xs">
            {findings.length ? findings.slice(0, 12).map((finding, index) => (
              <Stack key={`${finding.blockKey}-${finding.exercise}-${finding.lift}-${index}`} gap={2}>
                <Group gap={6}>
                  <Badge color="gray" variant="light" size="xs">{finding.label}</Badge>
                  <Badge color={directionColor(finding.direction)} variant="light" size="xs">{finding.direction}</Badge>
                  <Badge color="blue" variant="light" size="xs">{finding.strength}</Badge>
                </Group>
                <Text fz="sm">
                  <Text span fw={500}>{finding.exercise}</Text> → {finding.lift}
                </Text>
                <Text fz="xs" c="dimmed">{finding.reasoning || finding.caveat}</Text>
              </Stack>
            )) : (
              <Text fz="sm" c="dimmed">No block correlation reports were found for the selected blocks.</Text>
            )}
          </Stack>
        </Paper>
      </SimpleGrid>
    </Stack>
  )
}

export function LifetimeComparePanel({ unit }: { unit: WeightUnit }) {
  const [blocks, setBlocks] = useState<ProgramBlockIndexEntry[]>([])
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [comparison, setComparison] = useState<AiBlockComparisonResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const currentBlock = useMemo(() => blocks.find((block) => block.isCurrent) ?? null, [blocks])
  const selectableBlocks = useMemo(() => sortedPastBlocks(blocks).filter((block) => block.cacheStatus?.cached), [blocks])
  const sourceComparison = comparison?.deterministic ?? null
  const hasSourceBlocks = Boolean(currentBlock?.cacheStatus?.cached) || selectedKeys.length > 0
  const isMissingAiResult = comparison?.report?.cache_miss === true

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchProgramBlocks()
      .then((result) => {
        if (cancelled) return null
        const defaultKeys = result
          .filter((block) => !block.isCurrent && block.cacheStatus?.cached)
          .map((block) => block.blockKey)
        setBlocks(result)
        setSelectedKeys(defaultKeys)
        return fetchAiBlockComparison({
          blockKeys: defaultKeys,
          cacheOnly: true,
        })
      })
      .then((result) => {
        if (!cancelled && result) setComparison(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const runComparison = () => {
    setLoading(true)
    setError(null)
    fetchAiBlockComparison({
      blockKeys: selectedKeys,
      refresh: true,
      cacheOnly: false,
    })
      .then(setComparison)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  const setAllPastBlocks = () => {
    setSelectedKeys(blocks.filter((block) => !block.isCurrent && block.cacheStatus?.cached).map((block) => block.blockKey))
    setComparison(null)
  }

  const trendLines = sourceComparison ? trendBlockLines(sourceComparison) : []
  const e1rmTrendData = sourceComparison ? trendChartData(sourceComparison, 'e1rmTotalKg', unit) : []
  const dotsTrendData = sourceComparison ? trendChartData(sourceComparison, 'estimatedDots', unit) : []
  const volumeTrendData = sourceComparison ? trendChartData(sourceComparison, 'volumeKg', unit) : []
  const trainingDaysTrendData = sourceComparison ? trendChartData(sourceComparison, 'trainingDays', unit) : []

  return (
    <Stack gap="md">
      {error && (
        <Paper withBorder p="md" style={{ borderColor: 'var(--mantine-color-red-4)' }}>
          <Text c="red">{error}</Text>
        </Paper>
      )}

      <Paper withBorder p="md">
        <Group justify="space-between" align="flex-start" mb="md">
          <Group gap="xs">
            <GitCompare size={18} />
            <Title order={3} fz="lg">Lifetime Compare</Title>
          </Group>
          <Group gap="xs">
            <Button size="xs" variant="light" onClick={setAllPastBlocks}>All saved past blocks</Button>
            <Button size="xs" leftSection={<Brain size={14} />} onClick={runComparison} disabled={!hasSourceBlocks || loading}>
              {comparison && !isMissingAiResult ? 'Regenerate AI Analysis' : 'Run AI Lifetime Analysis'}
            </Button>
          </Group>
        </Group>

        <Group gap="lg" align="flex-start">
          <Stack gap="xs" style={{ minWidth: 260 }}>
            {currentBlock ? (
              <Checkbox
                checked={Boolean(currentBlock.cacheStatus?.cached)}
                disabled
                label={`Current block-to-date (${currentBlock.label})`}
              />
            ) : (
              <Badge color="yellow" variant="light">No current block found</Badge>
            )}
            <Text fz="xs" c="dimmed">Uses saved block analyses as AI source input. Current block-to-date is included when available.</Text>
          </Stack>
          <Group gap="xs" wrap="wrap" style={{ flex: 1 }}>
            {selectableBlocks.length ? selectableBlocks.map((block) => (
              <Checkbox
                key={block.blockKey}
                checked={selectedKeys.includes(block.blockKey)}
                onChange={(event) => {
                  const checked = event.currentTarget.checked
                  setSelectedKeys((current) =>
                    checked
                      ? Array.from(new Set([...current, block.blockKey]))
                      : current.filter((key) => key !== block.blockKey),
                  )
                  setComparison(null)
                }}
                label={`${block.label}${block.linkedCompetition ? ` (${block.linkedCompetition.date})` : ' (training only)'}`}
              />
            )) : (
              <Text fz="sm" c="dimmed">No saved past block analyses are available yet.</Text>
            )}
          </Group>
        </Group>
      </Paper>

      {loading && <Center mih="12vh"><Loader size="sm" /></Center>}

      {comparison && !loading && (
        <>
          {!sourceComparison || sourceComparison.rows.length === 0 ? (
            <Paper withBorder p="lg">
              <Text fw={500}>No source analyses selected</Text>
              <Text fz="sm" c="dimmed">No current or past block analyses were available for comparison.</Text>
            </Paper>
          ) : (
            <Stack gap="md">
              {isMissingAiResult ? (
                <Paper withBorder p="lg">
                  <Group gap="xs" mb="xs">
                    <AlertTriangle size={18} />
                    <Text fw={500}>No saved AI lifetime analysis for this source set</Text>
                  </Group>
                  <Text fz="sm" c="dimmed">
                    Run the AI lifetime analysis to compare the selected block analyses. Opening this page does not generate a new report.
                  </Text>
                </Paper>
              ) : (
                <AiReportSection comparison={comparison} />
              )}

              <SimpleGrid cols={{ base: 1, lg: 2 }}>
                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm">
                    <BarChart3 size={18} />
                    <Text fw={500}>Estimated Total e1RM Trend</Text>
                  </Group>
                  <Box style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={e1rmTrendData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--mantine-color-default-border)" />
                        <XAxis dataKey="week" tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <YAxis tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: 'var(--mantine-color-body)',
                            border: '1px solid var(--mantine-color-default-border)',
                          }}
                        />
                        <Legend />
                        {trendLines.map((line) => (
                          <Line key={line.blockKey} type="monotone" dataKey={line.blockKey} name={line.label} stroke={line.color} strokeWidth={2} connectNulls={false} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                </Paper>

                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm">
                    <Trophy size={18} />
                    <Text fw={500}>Estimated DOTS Trend</Text>
                  </Group>
                  <Box style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={dotsTrendData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--mantine-color-default-border)" />
                        <XAxis dataKey="week" tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <YAxis tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: 'var(--mantine-color-body)',
                            border: '1px solid var(--mantine-color-default-border)',
                          }}
                        />
                        <Legend />
                        {trendLines.map((line) => (
                          <Line key={line.blockKey} type="monotone" dataKey={line.blockKey} name={line.label} stroke={line.color} strokeWidth={2} connectNulls={false} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                </Paper>

                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm">
                    <BarChart3 size={18} />
                    <Text fw={500}>Weekly Volume Trend</Text>
                  </Group>
                  <Box style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={volumeTrendData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--mantine-color-default-border)" />
                        <XAxis dataKey="week" tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <YAxis tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <RechartsTooltip contentStyle={{ backgroundColor: 'var(--mantine-color-body)', border: '1px solid var(--mantine-color-default-border)' }} />
                        <Legend />
                        {trendLines.map((line) => (
                          <Line key={line.blockKey} type="monotone" dataKey={line.blockKey} name={line.label} stroke={line.color} strokeWidth={2} connectNulls={false} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                </Paper>

                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm">
                    <CheckCircle size={18} />
                    <Text fw={500}>Training Days per Week</Text>
                  </Group>
                  <Box style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trainingDaysTrendData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--mantine-color-default-border)" />
                        <XAxis dataKey="week" tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <YAxis allowDecimals={false} tick={{ fill: 'var(--mantine-color-dimmed)' }} />
                        <RechartsTooltip contentStyle={{ backgroundColor: 'var(--mantine-color-body)', border: '1px solid var(--mantine-color-default-border)' }} />
                        <Legend />
                        {trendLines.map((line) => (
                          <Line key={line.blockKey} type="monotone" dataKey={line.blockKey} name={line.label} stroke={line.color} strokeWidth={2} connectNulls={false} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                </Paper>
              </SimpleGrid>

              <Paper withBorder p="md">
                <Group gap="xs" mb="sm">
                  <GitCompare size={18} />
                  <Text fw={500}>Block Comparison</Text>
                </Group>
                <Box style={{ overflowX: 'auto' }}>
                  <Table fz="sm">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Block</Table.Th>
                        <Table.Th>Competitions / Goals</Table.Th>
                        <Table.Th ta="right">Actual Total</Table.Th>
                        <Table.Th ta="right">DOTS</Table.Th>
                        <Table.Th ta="right">e1RM Delta</Table.Th>
                        <Table.Th ta="right">Compliance</Table.Th>
                        <Table.Th ta="right">Fatigue</Table.Th>
                        <Table.Th ta="right">Projection Delta</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {sourceComparison.rows.map((row) => (
                        <Table.Tr key={row.blockKey}>
                          <Table.Td>
                            <Text fw={500}>{row.label}</Text>
                            <Text fz="xs" c="dimmed">{row.startDate} to {row.endDate}</Text>
                          </Table.Td>
                          <Table.Td>
                            {(row.competitions?.length || row.goals?.length) ? (
                              <Stack gap={4}>
                                {row.competitions?.map((competition) => (
                                  <Stack key={`${competition.name}-${competition.date}`} gap={0}>
                                    <Group gap={4}>
                                      <Text fz="sm">{competition.name}</Text>
                                      <Badge color={competition.status === 'completed' ? 'green' : 'blue'} variant="light" size="xs">{competition.status}</Badge>
                                    </Group>
                                    <Text fz="xs" c="dimmed">
                                      {competition.date}
                                      {typeof competition.targetTotalKg === 'number' && ` · target ${kg(competition.targetTotalKg, unit)}`}
                                      {typeof competition.resultTotalKg === 'number' && ` · result ${kg(competition.resultTotalKg, unit)}`}
                                    </Text>
                                  </Stack>
                                ))}
                                {row.goals?.map((goal) => (
                                  <Text key={goal.id} fz="xs" c="dimmed">
                                    Goal: {goal.title}
                                    {typeof goal.targetTotalKg === 'number' && ` · ${kg(goal.targetTotalKg, unit)}`}
                                    {typeof goal.targetDots === 'number' && ` · ${goal.targetDots.toFixed(1)} DOTS`}
                                  </Text>
                                ))}
                              </Stack>
                            ) : (
                              <Badge color="gray" variant="light" size="sm">No comp/goal context</Badge>
                            )}
                          </Table.Td>
                          <Table.Td ta="right">{kg(row.actualTotalKg, unit)}</Table.Td>
                          <Table.Td ta="right">
                            {row.actualDots != null ? metric(row.actualDots, 2) : row.estimatedDots != null ? `${metric(row.estimatedDots, 2)} est.` : '--'}
                          </Table.Td>
                          <Table.Td ta="right">{kg(row.e1rmDeltaKg, unit)}</Table.Td>
                          <Table.Td ta="right">{percent(row.compliancePct)}</Table.Td>
                          <Table.Td ta="right">{percent(row.fatigueIndex, 100)}</Table.Td>
                          <Table.Td ta="right">{kg(row.projectionTotalDeltaKg, unit)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Box>
              </Paper>

              <SimpleGrid cols={{ base: 1, lg: 2 }}>
                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm">
                    <BarChart3 size={18} />
                    <Text fw={500}>Volume Dose Response by Lift</Text>
                  </Group>
                  <Box style={{ overflowX: 'auto' }}>
                    <Table fz="sm">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Block</Table.Th>
                          <Table.Th>Lift</Table.Th>
                          <Table.Th ta="right">Avg INOL</Table.Th>
                          <Table.Th ta="right">Sets</Table.Th>
                          <Table.Th ta="right">Volume</Table.Th>
                          <Table.Th ta="right">Delta</Table.Th>
                          <Table.Th ta="right">kg / 1k volume</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {(sourceComparison.liftDoseResponse ?? []).map((row) => (
                          <Table.Tr key={`${row.blockKey}-${row.lift}`}>
                            <Table.Td>{row.label}</Table.Td>
                            <Table.Td tt="capitalize">{row.lift}</Table.Td>
                            <Table.Td ta="right">{metric(row.avgInol, 2)}</Table.Td>
                            <Table.Td ta="right">{row.sets}</Table.Td>
                            <Table.Td ta="right">{kg(row.volumeKg, unit)}</Table.Td>
                            <Table.Td ta="right">{kg(row.strengthDeltaKg, unit)}</Table.Td>
                            <Table.Td ta="right">{metric(row.responsePer1000Kg, 3)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                </Paper>

                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm">
                    <Database size={18} />
                    <Text fw={500}>Training Days vs Progress</Text>
                  </Group>
                  <Box style={{ overflowX: 'auto' }}>
                    <Table fz="sm">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Block</Table.Th>
                          <Table.Th ta="right">Weeks</Table.Th>
                          <Table.Th ta="right">Training Days</Table.Th>
                          <Table.Th ta="right">Avg Days/Wk</Table.Th>
                          <Table.Th ta="right">Total Delta</Table.Th>
                          <Table.Th ta="right">Compliance</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {(sourceComparison.trainingDayResponse ?? []).map((row) => (
                          <Table.Tr key={row.blockKey}>
                            <Table.Td>{row.label}</Table.Td>
                            <Table.Td ta="right">{row.completedWeeks}</Table.Td>
                            <Table.Td ta="right">{row.totalTrainingDays}</Table.Td>
                            <Table.Td ta="right">{metric(row.avgTrainingDaysPerWeek, 2)}</Table.Td>
                            <Table.Td ta="right">{kg(row.strengthDeltaKg, unit)}</Table.Td>
                            <Table.Td ta="right">{percent(row.compliancePct)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                </Paper>
              </SimpleGrid>

              <ConsolidatedRoiSection comparison={sourceComparison} unit={unit} />
            </Stack>
          )}
        </>
      )}
    </Stack>
  )
}
