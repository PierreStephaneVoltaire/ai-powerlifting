import * as XLSX from 'xlsx'
import type {
  BlockAnalysisBundle,
  BlockCompetitionOutcome,
  DataQualityFlag,
} from './blockAnalytics'

type Cell = string | number | null
type Row = Cell[]
type Format = 'xlsx' | 'markdown'

const LIFTS = ['squat', 'bench', 'deadlift', 'total'] as const
const EXPORT_CONTENT_TYPES: Record<Format, string> = {
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  markdown: 'text/markdown; charset=utf-8',
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function formatNumber(value: unknown, digits = 1): string {
  const numberValue = asNumber(value)
  return numberValue === null ? '--' : numberValue.toFixed(digits)
}

function formatKg(value: unknown): string {
  const numberValue = asNumber(value)
  return numberValue === null ? '--' : `${numberValue.toFixed(1)} kg`
}

function formatPct(value: unknown, multiplier = 100): string {
  const numberValue = asNumber(value)
  return numberValue === null ? '--' : `${(numberValue * multiplier).toFixed(1)}%`
}

function formatRawPct(value: unknown): string {
  const numberValue = asNumber(value)
  return numberValue === null ? '--' : `${numberValue.toFixed(1)}%`
}

function titleize(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function compactValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(compactValue).filter(Boolean).join('; ')

  const record = asRecord(value)
  const preferred = [
    'block',
    'lift',
    'finding',
    'change',
    'experiment',
    'reason',
    'why',
    'evidence',
    'tradeoff',
    'risk',
    'success_metric',
    'confidence',
  ]
    .map((key) => record[key])
    .map(compactValue)
    .filter(Boolean)

  return preferred.length ? preferred.join(' - ') : JSON.stringify(value)
}

function markdownEscape(value: unknown): string {
  return compactValue(value).replace(/\|/g, '\\|').replace(/\n/g, '<br>')
}

function markdownTable(headers: string[], rows: Row[]): string[] {
  if (!rows.length) return []
  return [
    `| ${headers.join(' | ')} |`,
    `| ${headers.map(() => '---').join(' | ')} |`,
    ...rows.map((row) => `| ${row.map(markdownEscape).join(' | ')} |`),
  ]
}

function sheetName(name: string, used: Set<string>): string {
  const base = name.replace(/[\\/?*[\]:]/g, ' ').slice(0, 31).trim() || 'Sheet'
  let candidate = base
  let suffix = 2
  while (used.has(candidate)) {
    const tail = ` ${suffix}`
    candidate = `${base.slice(0, 31 - tail.length)}${tail}`
    suffix += 1
  }
  used.add(candidate)
  return candidate
}

function appendSheet(workbook: XLSX.WorkBook, used: Set<string>, name: string, rows: Row[]): void {
  const sheet = XLSX.utils.aoa_to_sheet(rows)
  XLSX.utils.book_append_sheet(workbook, sheet, sheetName(name, used))
}

function blockExportStem(bundle: BlockAnalysisBundle): string {
  const label = bundle.block.label || bundle.block.block || bundle.block.blockKey
  const clean = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
  return `block-analysis-${clean || bundle.block.blockKey}`
}

export function blockAnalysisExportFilename(bundle: BlockAnalysisBundle, format: Format): string {
  return `${blockExportStem(bundle)}.${format === 'xlsx' ? 'xlsx' : 'md'}`
}

export function blockAnalysisExportContentType(format: Format): string {
  return EXPORT_CONTENT_TYPES[format]
}

function summaryRows(bundle: BlockAnalysisBundle): Row[] {
  const block = bundle.block
  const summary = bundle.historical.analyticsSummary
  return [
    ['Metric', 'Value'],
    ['Block', block.label],
    ['Date range', `${block.startDate} to ${block.endDate}`],
    ['Weeks', block.weekCount],
    ['Week range', `W${block.weekStart}-W${block.weekEnd}`],
    ['Sessions', `${block.completedSessions}/${block.totalSessions} completed`],
    ['Completed sessions analyzed', summary.sessionsAnalyzed],
    ['Compliance', formatRawPct(summary.compliancePct)],
    ['Total completed volume', formatKg(summary.totalVolumeKg)],
    ['Fatigue index', formatPct(summary.fatigueIndex)],
    ['ACWR composite', formatNumber(summary.acwrComposite, 2)],
    ['Training only', block.trainingOnly ? 'Yes' : 'No'],
    ['Generated', bundle.generatedAt],
  ]
}

function startMaxRows(bundle: BlockAnalysisBundle): Row[] {
  const manual = bundle.historical.manualStartMaxes
  const strength = bundle.historical.startStrength
  const manualValues = {
    squat: manual?.squat_kg,
    bench: manual?.bench_kg,
    deadlift: manual?.deadlift_kg,
    total: manual?.total_kg,
  }
  return [
    ['Lift', 'Start max', 'Source'],
    ...LIFTS.map((lift) => [
      titleize(lift),
      formatKg(manualValues[lift] ?? strength[lift]),
      lift === 'total' && manual?.total_kg == null ? bundle.historical.startMaxesSource : bundle.historical.startMaxesSource,
    ]),
    ['Updated', manual?.updated_at ?? '', manual ? 'Manual entry' : ''],
  ]
}

function strengthRows(bundle: BlockAnalysisBundle): Row[] {
  const historical = bundle.historical
  return [
    ['Lift', 'Start', 'End', 'Delta'],
    ...LIFTS.map((lift) => [
      titleize(lift),
      formatKg(historical.startStrength[lift]),
      formatKg(historical.endStrength[lift]),
      formatKg(historical.strengthDelta[lift]),
    ]),
  ]
}

function competitionRows(outcome: BlockCompetitionOutcome | null): Row[] {
  if (!outcome) return [['Metric', 'Value'], ['Competition', 'No completed competition maps to this block.']]
  const rows: Row[] = [
    ['Metric', 'Value'],
    ['Competition', outcome.competitionName],
    ['Date', outcome.competitionDate],
    ['Bodyweight', formatKg(outcome.bodyweightKg)],
    ['Actual total', formatKg(outcome.results?.total_kg)],
    ['DOTS', formatNumber(outcome.dots, 2)],
    ['IPF GL', formatNumber(outcome.ipfGl, 2)],
    ['Post-meet report captured', outcome.postMeetReportCaptured ? 'Yes' : 'No'],
  ]

  if (outcome.results) {
    rows.push(
      ['Actual squat', formatKg(outcome.results.squat_kg)],
      ['Actual bench', formatKg(outcome.results.bench_kg)],
      ['Actual deadlift', formatKg(outcome.results.deadlift_kg)],
    )
  }

  if (outcome.projectionAccuracy) {
    rows.push(['Projection accuracy', 'Actual / projected / delta'])
    for (const [key, item] of Object.entries(outcome.projectionAccuracy)) {
      rows.push([
        titleize(key.replace('_kg', '')),
        `${formatKg(item.actualKg)} / ${formatKg(item.projectedKg)} / ${formatKg(item.deltaKg)}`,
      ])
    }
  }

  return rows
}

function dataQualityRows(flags: DataQualityFlag[]): Row[] {
  if (!flags.length) return [['Severity', 'Code', 'Label'], ['complete', '', 'Complete']]
  return [
    ['Severity', 'Code', 'Label'],
    ...flags.map((flag) => [flag.severity, flag.code, flag.label]),
  ]
}

function liftMetricRows(weekly: Record<string, unknown>): Row[] {
  const lifts = asRecord(weekly.lifts)
  const rows: Row[] = [['Lift', 'Progression kg/wk', 'Fit quality', 'Volume change', 'Intensity change', 'Failed sets', 'RPE trend']]
  for (const [lift, raw] of Object.entries(lifts)) {
    const metrics = asRecord(raw)
    rows.push([
      titleize(lift),
      formatNumber(metrics.progression_rate_kg_per_week, 2),
      formatNumber(metrics.fit_quality, 2),
      formatRawPct(metrics.volume_change_pct),
      formatRawPct(metrics.intensity_change_pct),
      asNumber(metrics.failed_sets) ?? '',
      asString(metrics.rpe_trend),
    ])
  }
  return rows
}

function weeklySummaryRows(weekly: Record<string, unknown>): Row[] {
  const compliance = asRecord(weekly.compliance)
  const currentMaxes = asRecord(weekly.current_maxes)
  const fatigueComponents = asRecord(weekly.fatigue_components)
  return [
    ['Metric', 'Value'],
    ['Block', asString(weekly.block)],
    ['Selected weeks', `${weekly.selected_week_start ?? ''}-${weekly.selected_week_end ?? ''}`],
    ['Window', `${weekly.window_start ?? ''} to ${weekly.window_end ?? ''}`],
    ['Sessions analyzed', asNumber(weekly.sessions_analyzed) ?? ''],
    ['Compliance', compliance.pct !== undefined ? formatRawPct(compliance.pct) : '--'],
    ['Current squat', formatKg(currentMaxes.squat)],
    ['Current bench', formatKg(currentMaxes.bench)],
    ['Current deadlift', formatKg(currentMaxes.deadlift)],
    ['Estimated DOTS', formatNumber(weekly.estimated_dots, 2)],
    ['Fatigue index', formatPct(weekly.fatigue_index)],
    ['Window mean fatigue', formatPct(fatigueComponents.window_mean_fi)],
    ['Window peak fatigue', formatPct(fatigueComponents.window_peak_fi)],
    ['Projection reason', asString(weekly.projection_reason)],
  ]
}

function inolRows(weekly: Record<string, unknown>): Row[] {
  const inol = asRecord(weekly.inol)
  const avg = asRecord(inol.avg_inol)
  const raw = asRecord(inol.raw_avg_inol)
  const coefficients = asRecord(inol.stimulus_coefficients)
  if (!Object.keys(avg).length) return []
  return [
    ['Lift', 'Adjusted INOL', 'Raw INOL', 'Stimulus coefficient'],
    ...Object.entries(avg).map(([lift, value]) => [
      titleize(lift),
      formatNumber(value, 2),
      formatNumber(raw[lift], 2),
      formatNumber(coefficients[lift], 2),
    ]),
  ]
}

function acwrRows(weekly: Record<string, unknown>): Row[] {
  const acwr = asRecord(weekly.acwr)
  if (!Object.keys(acwr).length) return []
  if (acwr.status === 'insufficient_data') {
    return [['Metric', 'Value'], ['Status', 'Insufficient data'], ['Reason', asString(acwr.reason)]]
  }

  const rows: Row[] = [
    ['Dimension', 'Value', 'Zone', 'Label'],
    ['Composite', formatNumber(acwr.composite, 2), asString(acwr.composite_zone), asString(acwr.composite_label)],
  ]
  for (const [dimension, raw] of Object.entries(asRecord(acwr.dimensions))) {
    const info = asRecord(raw)
    rows.push([
      titleize(dimension),
      formatNumber(info.value, 2),
      asString(info.zone),
      asString(info.label),
    ])
  }
  return rows
}

function projectionsRows(weekly: Record<string, unknown>): Row[] {
  const projections = asArray(weekly.projections).map(asRecord).filter((projection) => Object.keys(projection).length)
  if (!projections.length) return []
  return [
    ['Competition', 'Projected total', 'Confidence', 'Weeks to comp', 'Method'],
    ...projections.map((projection) => [
      asString(projection.comp_name) || 'Projected total',
      formatKg(projection.total),
      formatPct(projection.confidence),
      formatNumber(projection.weeks_to_comp, 1),
      asString(projection.method),
    ]),
  ]
}

function exerciseStatsRows(weekly: Record<string, unknown>): Row[] {
  const stats = asRecord(weekly.exercise_stats)
  if (!Object.keys(stats).length) return []
  return [
    ['Exercise', 'Sets', 'Volume', 'Max kg'],
    ...Object.entries(stats).map(([exercise, raw]) => {
      const item = asRecord(raw)
      return [
        exercise,
        asNumber(item.total_sets) ?? '',
        formatKg(item.total_volume),
        formatKg(item.max_kg),
      ]
    }),
  ]
}

function alertsRows(weekly: Record<string, unknown>): Row[] {
  const alerts = asArray(weekly.alerts).map(asRecord)
  if (!alerts.length) return []
  return [
    ['Severity', 'Source', 'Message', 'Detail'],
    ...alerts.map((alert) => [
      asString(alert.severity),
      asString(alert.source),
      asString(alert.message),
      asString(alert.raw_detail),
    ]),
  ]
}

function programEvaluationRows(programEvaluation: Record<string, unknown> | null): Row[] {
  if (!programEvaluation) return [['Section', 'Text'], ['Program Analysis', 'No cached program analysis for this block.']]

  const rows: Row[] = [
    ['Section', 'Text'],
    ['Summary', asString(programEvaluation.summary) || asString(programEvaluation.insufficient_data_reason)],
  ]

  const sections = [
    ['Working', programEvaluation.what_is_working],
    ['Not Working', programEvaluation.what_is_not_working],
    ['Adjustments', programEvaluation.small_changes],
    ['Monitoring', programEvaluation.monitoring_focus],
    ['Conclusion', programEvaluation.conclusion],
  ] as const

  for (const [label, value] of sections) {
    if (Array.isArray(value)) {
      value.forEach((item) => rows.push([label, compactValue(item)]))
    } else if (value) {
      rows.push([label, compactValue(value)])
    }
  }

  return rows
}

function correlationRows(correlation: Record<string, unknown> | null): Row[] {
  if (!correlation) return [['Exercise', 'Lift', 'Direction', 'Strength', 'Reasoning', 'Caveat'], ['No cached ROI correlation report for this block.', '', '', '', '', '']]
  const rows: Row[] = [
    ['Exercise', 'Lift', 'Direction', 'Strength', 'Reasoning', 'Caveat'],
  ]
  const findings = asArray(correlation.findings).map(asRecord)
  if (!findings.length) {
    rows.push([asString(correlation.summary) || asString(correlation.insufficient_data_reason) || 'No findings.', '', '', '', '', ''])
    return rows
  }
  for (const finding of findings) {
    rows.push([
      asString(finding.exercise),
      asString(finding.lift),
      asString(finding.correlation_direction),
      asString(finding.strength),
      asString(finding.reasoning),
      asString(finding.caveat),
    ])
  }
  return rows
}

function riRows(weekly: Record<string, unknown>): Row[] {
  const distribution = asRecord(weekly.ri_distribution)
  const overall = asRecord(distribution.overall)
  if (!Object.keys(overall).length) return []
  return [
    ['Bucket', 'Count', 'Percent'],
    ...Object.entries(overall).map(([bucket, raw]) => {
      const item = asRecord(raw)
      return [titleize(bucket), asNumber(item.count) ?? '', formatRawPct(item.pct)]
    }),
  ]
}

function specificityRows(weekly: Record<string, unknown>): Row[] {
  const specificity = asRecord(weekly.specificity_ratio)
  if (!Object.keys(specificity).length) return []
  return [
    ['Metric', 'Value'],
    ['Narrow', formatPct(specificity.narrow)],
    ['Broad', formatPct(specificity.broad)],
    ['Total sets', asNumber(specificity.total_sets) ?? ''],
    ['SBD sets', asNumber(specificity.sbd_sets) ?? ''],
    ['Secondary sets', asNumber(specificity.secondary_sets) ?? ''],
    ['Narrow status', asString(specificity.narrow_status)],
    ['Broad status', asString(specificity.broad_status)],
  ]
}

function fatigueDimensionRows(weekly: Record<string, unknown>): Row[] {
  const dimensions = asRecord(asRecord(weekly.fatigue_dimensions).weekly)
  if (!Object.keys(dimensions).length) return []
  return [
    ['Week', 'Axial', 'Neural', 'Peripheral', 'Systemic'],
    ...Object.entries(dimensions)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([week, raw]) => {
        const item = asRecord(raw)
        return [
          `W${week}`,
          formatNumber(item.axial, 1),
          formatNumber(item.neural, 1),
          formatNumber(item.peripheral, 1),
          formatNumber(item.systemic, 1),
        ]
      }),
  ]
}

export function buildBlockAnalysisMarkdownExport(
  bundle: BlockAnalysisBundle,
  programEvaluation: Record<string, unknown> | null,
  correlation: Record<string, unknown> | null,
): string {
  const weekly = asRecord(bundle.weekly)
  const sections: string[] = [
    `# ${bundle.block.label} Block Analysis`,
    '',
    `Generated: ${new Date().toISOString()}`,
    `Cached analysis generated: ${bundle.generatedAt}`,
    '',
    '## Summary',
    ...markdownTable(summaryRows(bundle)[0].map(String), summaryRows(bundle).slice(1)),
    '',
    '## Block Start Maxes',
    ...markdownTable(startMaxRows(bundle)[0].map(String), startMaxRows(bundle).slice(1)),
    '',
    '## Strength Start / End',
    ...markdownTable(strengthRows(bundle)[0].map(String), strengthRows(bundle).slice(1)),
    '',
    '## Competition Outcome',
    ...markdownTable(competitionRows(bundle.historical.competitionOutcome)[0].map(String), competitionRows(bundle.historical.competitionOutcome).slice(1)),
    '',
    '## Data Quality',
    ...markdownTable(dataQualityRows(bundle.historical.missingData)[0].map(String), dataQualityRows(bundle.historical.missingData).slice(1)),
    '',
    '## Weekly Analysis',
    ...markdownTable(weeklySummaryRows(weekly)[0].map(String), weeklySummaryRows(weekly).slice(1)),
    '',
    '## Lift Metrics',
    ...markdownTable(liftMetricRows(weekly)[0].map(String), liftMetricRows(weekly).slice(1)),
  ]

  const optionalTables: Array<[string, Row[]]> = [
    ['Stimulus-Adjusted INOL', inolRows(weekly)],
    ['EWMA ACWR', acwrRows(weekly)],
    ['Relative Intensity Distribution', riRows(weekly)],
    ['Specificity Ratio', specificityRows(weekly)],
    ['Fatigue Dimensions', fatigueDimensionRows(weekly)],
    ['Projections', projectionsRows(weekly)],
    ['Alerts', alertsRows(weekly)],
    ['Exercise Stats', exerciseStatsRows(weekly)],
    ['Program Analysis', programEvaluationRows(programEvaluation)],
    ['Exercise ROI Correlation', correlationRows(correlation)],
  ]

  for (const [title, rows] of optionalTables) {
    if (!rows.length) continue
    sections.push('', `## ${title}`, ...markdownTable(rows[0].map(String), rows.slice(1)))
  }

  return `${sections.join('\n')}\n`
}

export function buildBlockAnalysisWorkbookExport(
  bundle: BlockAnalysisBundle,
  programEvaluation: Record<string, unknown> | null,
  correlation: Record<string, unknown> | null,
): Buffer {
  const weekly = asRecord(bundle.weekly)
  const workbook = XLSX.utils.book_new()
  const used = new Set<string>()

  appendSheet(workbook, used, 'Summary', summaryRows(bundle))
  appendSheet(workbook, used, 'Start Maxes', startMaxRows(bundle))
  appendSheet(workbook, used, 'Strength', strengthRows(bundle))
  appendSheet(workbook, used, 'Competition', competitionRows(bundle.historical.competitionOutcome))
  appendSheet(workbook, used, 'Data Quality', dataQualityRows(bundle.historical.missingData))
  appendSheet(workbook, used, 'Weekly Analysis', weeklySummaryRows(weekly))
  appendSheet(workbook, used, 'Lift Metrics', liftMetricRows(weekly))

  const optionalSheets: Array<[string, Row[]]> = [
    ['INOL', inolRows(weekly)],
    ['ACWR', acwrRows(weekly)],
    ['RI Distribution', riRows(weekly)],
    ['Specificity', specificityRows(weekly)],
    ['Fatigue Dimensions', fatigueDimensionRows(weekly)],
    ['Projections', projectionsRows(weekly)],
    ['Alerts', alertsRows(weekly)],
    ['Exercise Stats', exerciseStatsRows(weekly)],
    ['Program Analysis', programEvaluationRows(programEvaluation)],
    ['ROI Correlation', correlationRows(correlation)],
  ]

  for (const [name, rows] of optionalSheets) {
    if (rows.length) appendSheet(workbook, used, name, rows)
  }

  return XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' }) as Buffer
}
