import { useState, useEffect } from 'react';
import { useProgramStore } from '@/store/programStore';
import { fetchCorrelationReport, fetchProgramEvaluation, type CorrelationReport, type ProgramEvaluationReport } from '@/api/analytics';
import { Paper, Group, Text, Badge, Loader, Box, Table, Stack, SimpleGrid } from '@mantine/core';
import { Brain, Trophy } from 'lucide-react';

const CORR_DIR_BADGE: Record<string, string> = {
  positive: 'green',
  negative: 'red',
  unclear: 'gray',
};

const CORR_STRENGTH_BADGE: Record<string, string> = {
  strong: 'violet',
  moderate: 'blue',
  weak: 'gray',
};

interface AiAnalysisProps {
  effectiveWeeks: number;
  weeksMode: number | 'current' | 'block';
  /** When true, the parent is running a full regeneration — show spinners and reload when it completes. */
  isRegenerating?: boolean;
}

export function AiAnalysis({ effectiveWeeks, weeksMode, isRegenerating = false }: AiAnalysisProps) {
  const { program } = useProgramStore();

  // Correlation report state
  const [corrReport, setCorrReport] = useState<CorrelationReport | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);
  const [corrError, setCorrError] = useState<string | null>(null);

  // Program evaluation state
  const [evalReport, setEvalReport] = useState<ProgramEvaluationReport | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // Fetch correlation report when weeks >= 4, then fetch program evaluation sequentially.
  // Also re-fetches after a regeneration completes (isRegenerating transitions false→true→false).
  useEffect(() => {
    if (isRegenerating) return;

    if (effectiveWeeks < 4) {
      setCorrReport(null);
      setCorrLoading(false);
      return;
    }

    let cancelled = false;
    setCorrLoading(true);
    setCorrError(null);
    fetchCorrelationReport(effectiveWeeks, 'current', false, true)
      .then((report) => {
        if (cancelled) return;
        setCorrReport(report);
        setCorrLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setCorrError(e.message);
        setCorrLoading(false);
      });

    return () => { cancelled = true; };
  }, [effectiveWeeks, isRegenerating]);

  // Program evaluation — fetch when in Full Block mode, after correlation completes.
  useEffect(() => {
    if (weeksMode !== 'block') {
      setEvalReport(null);
      setEvalError(null);
      return;
    }
    if (isRegenerating) return;
    if (corrLoading) return;
    const completedCount = (program?.sessions ?? []).filter(
      s => (s.block ?? 'current') === 'current' && s.completed,
    ).length;
    if (completedCount < 4) {
      setEvalReport(null);
      return;
    }
    setEvalLoading(true);
    setEvalError(null);
    fetchProgramEvaluation(false, true)
      .then(setEvalReport)
      .catch((e) => setEvalError(e.message))
      .finally(() => setEvalLoading(false));
  }, [weeksMode, program?.meta?.program_start, program?.sessions, isRegenerating, corrLoading]);

  const STANCE_COLORS: Record<string, string> = { continue: 'green', monitor: 'blue', adjust: 'yellow', critical: 'red' };
  const ALIGN_COLORS: Record<string, string> = { good: 'green', mixed: 'yellow', poor: 'red' };
  const PRIORITY_COLORS: Record<string, string> = { low: 'gray', moderate: 'yellow', high: 'red' };
  const GOAL_STATUS_COLORS: Record<string, string> = { achieved: 'green', on_track: 'blue', at_risk: 'yellow', off_track: 'red', unclear: 'gray' };
  const GOAL_PRIORITY_COLORS: Record<string, string> = { primary: 'red', secondary: 'blue', optional: 'gray' };
  const COMPETITION_PRIORITY_COLORS: Record<string, string> = { prioritize: 'red', supporting: 'blue', practice: 'gray', deprioritize: 'yellow', drop: 'red' };
  const WEIGHT_CLASS_COLORS: Record<string, string> = { best: 'green', viable: 'blue', risky: 'yellow' };

  const completedCount = (program?.sessions ?? []).filter(
    s => (s.block ?? 'current') === 'current' && s.completed,
  ).length;
  const corrFindings = corrReport?.findings ?? [];
  const goalStatuses = evalReport?.goal_status ?? [];
  const competitionAlignment = evalReport?.competition_alignment ?? [];
  const competitionStrategy = evalReport?.competition_strategy ?? [];
  const weightClassStrategy = evalReport?.weight_class_strategy ?? {
    recommendation: '',
    recommended_weight_class_kg: null,
    viable_options: [],
  };
  const workingItems = evalReport?.what_is_working ?? [];
  const blockedItems = evalReport?.what_is_not_working ?? [];
  const smallChanges = evalReport?.small_changes ?? [];
  const externalFactors = evalReport?.external_factors ?? [];
  const monitoringFocus = evalReport?.monitoring_focus ?? [];

  return (
    <>
      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <Brain size={18} />
            <Text fw={500}>Exercise ROI Correlation</Text>
            {isRegenerating ? (
              <Badge color="orange" variant="light" size="sm">Regenerating…</Badge>
            ) : corrReport && (
              <Badge color={corrReport.cached ? 'blue' : 'green'} variant="light" size="sm">
                {corrReport.cached ? `Cached ${corrReport.generated_at ? new Date(corrReport.generated_at).toLocaleDateString() : ''}` : 'Just generated'}
              </Badge>
            )}
          </Group>
        </Group>

        {effectiveWeeks < 4 ? (
          <Text size="sm" c="dimmed">Correlation analysis requires at least 4 weeks of data. Select 4+ weeks or Full Block.</Text>
        ) : isRegenerating || corrLoading ? (
          <Group gap="xs" py="md">
            <Loader size="xs" />
            <Text size="sm" c="dimmed">{isRegenerating ? 'Regenerating AI analysis…' : 'Loading cached ROI analysis…'}</Text>
          </Group>
        ) : corrError ? (
          <Text size="sm" c="red">{corrError}</Text>
        ) : corrReport ? (
          <>
            {corrReport.insufficient_data ? (
              <Text size="sm" c="dimmed">{corrReport.insufficient_data_reason || 'Insufficient data for meaningful correlation analysis.'}</Text>
            ) : (
              <>
                {corrReport.summary && (
                  <Text size="sm" c="dimmed" mb="md" p="sm" fs="italic" style={{ background: 'var(--mantine-color-default-hover)', borderRadius: 'var(--mantine-radius-sm)' }}>{corrReport.summary}</Text>
                )}
                {corrFindings.length > 0 ? (
                  <Box style={{ overflowX: 'auto' }}>
                    <Table fz="sm">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th ta="left">Exercise</Table.Th>
                          <Table.Th ta="left">→ Lift</Table.Th>
                          <Table.Th ta="left" w={{ base: 'auto', sm: 100 }}>Direction</Table.Th>
                          <Table.Th ta="left" w={{ base: 'auto', sm: 100 }}>Strength</Table.Th>
                          <Table.Th ta="left" visibleFrom="sm">Reasoning</Table.Th>
                          <Table.Th ta="left" visibleFrom="sm">Caveat</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {corrFindings.map((f, i) => (
                          <Table.Tr key={i} style={{ verticalAlign: 'top' }}>
                            <Table.Td fw={500}>{f.exercise}</Table.Td>
                            <Table.Td>{f.lift}</Table.Td>
                            <Table.Td>
                              <Badge size="xs" variant="light" color={CORR_DIR_BADGE[f.correlation_direction] || 'gray'} style={{ textTransform: 'capitalize' }}>
                                {f.correlation_direction}
                              </Badge>
                            </Table.Td>
                            <Table.Td>
                              <Badge size="xs" variant="light" color={CORR_STRENGTH_BADGE[f.strength] || 'gray'} style={{ textTransform: 'capitalize' }}>
                                {f.strength}
                              </Badge>
                            </Table.Td>
                            <Table.Td fz="xs" visibleFrom="sm">{f.reasoning}</Table.Td>
                            <Table.Td c="dimmed" fz="xs" fs="italic" visibleFrom="sm">{f.caveat}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                ) : (
                  <Text size="sm" c="dimmed">No significant anatomically-relevant correlations found in this window.</Text>
                )}
              </>
            )}
          </>
        ) : null}
      </Paper>

      {weeksMode === 'block' && (
        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <Trophy size={18} />
              <Text fw={500}>Program Evaluation</Text>
              {isRegenerating ? (
                <Badge color="orange" variant="light" size="sm">Regenerating…</Badge>
              ) : evalReport && (
                <Badge color={evalReport.cached ? 'blue' : 'green'} variant="light" size="sm">
                  {evalReport.cached ? `Cached ${evalReport.generated_at ? new Date(evalReport.generated_at).toLocaleDateString() : ''}` : 'Just generated'}
                </Badge>
              )}
              {evalReport?.stance && !isRegenerating && (
                <Badge color={STANCE_COLORS[evalReport.stance] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize' }}>
                  {evalReport.stance}
                </Badge>
              )}
            </Group>
          </Group>

          {completedCount < 4 ? (
            <Text size="sm" c="dimmed">Program evaluation requires at least 4 completed sessions in the current block. Complete more sessions and return here.</Text>
          ) : isRegenerating || evalLoading ? (
            <Group gap="xs" py="md">
              <Loader size="xs" />
              <Text size="sm" c="dimmed">{isRegenerating ? 'Regenerating AI analysis…' : 'Loading cached program evaluation…'}</Text>
            </Group>
          ) : evalError ? (
            <Text size="sm" c="red">{evalError}</Text>
          ) : evalReport ? (
            <>
              {evalReport.insufficient_data ? (
                <Text size="sm" c="dimmed">{evalReport.insufficient_data_reason || 'Insufficient data for program evaluation.'}</Text>
              ) : (
                <Stack gap="md">
                  {evalReport.summary && (
                    <Text size="sm" c="dimmed" p="sm" fs="italic" style={{ background: 'var(--mantine-color-default-hover)', borderRadius: 'var(--mantine-radius-sm)' }}>{evalReport.summary}</Text>
                  )}

                  {goalStatuses.length > 0 && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>Goal Status</Text>
                      <Stack gap="xs">
                        {goalStatuses.map((goal, i) => (
                          <Group key={i} gap="sm" align="flex-start" p="xs" style={{ background: 'var(--mantine-color-default-hover)', borderRadius: 'var(--mantine-radius-sm)' }}>
                            <Badge color={GOAL_STATUS_COLORS[goal.status] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize', marginTop: 2 }}>
                              {goal.status.replace('_', ' ')}
                            </Badge>
                            <Stack gap={2}>
                              <Group gap={6}>
                                <Text size="sm" fw={500}>{goal.goal}</Text>
                                <Badge color={GOAL_PRIORITY_COLORS[goal.priority] || 'gray'} variant="light" size="xs" style={{ textTransform: 'capitalize' }}>
                                  {goal.priority}
                                </Badge>
                              </Group>
                              <Text size="xs" c="dimmed">{goal.reason}</Text>
                            </Stack>
                          </Group>
                        ))}
                      </Stack>
                    </Stack>
                  )}

                  {competitionAlignment.length > 0 && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>Competition Alignment</Text>
                      <Stack gap="xs">
                        {competitionAlignment.map((ca, i) => (
                          <Group key={i} gap="sm" align="flex-start" p="xs" style={{ background: 'var(--mantine-color-default-hover)', borderRadius: 'var(--mantine-radius-sm)' }}>
                            <Badge color={ALIGN_COLORS[ca.alignment] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize', marginTop: 2 }}>{ca.alignment}</Badge>
                            <Stack gap={2}>
                              <Text size="sm" fw={500}>{ca.competition} <Text span size="xs" c="dimmed">({ca.role}{typeof ca.weeks_to_comp === 'number' ? `, ${ca.weeks_to_comp.toFixed(1)} wks out` : ''})</Text></Text>
                              <Text size="xs" c="dimmed">{ca.reason}</Text>
                            </Stack>
                          </Group>
                        ))}
                      </Stack>
                    </Stack>
                  )}

                  {competitionStrategy.length > 0 && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>Competition Strategy</Text>
                      <Stack gap="xs">
                        {competitionStrategy.map((strategy, i) => (
                          <Paper key={i} withBorder p="sm">
                            <Group gap="xs" mb={4} wrap="wrap">
                              <Text size="sm" fw={500}>{strategy.competition}</Text>
                              <Badge color={COMPETITION_PRIORITY_COLORS[strategy.priority] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize' }}>
                                {strategy.priority}
                              </Badge>
                              <Badge color="grape" variant="light" size="sm" style={{ textTransform: 'capitalize' }}>
                                {strategy.approach.replace('_', ' ')}
                              </Badge>
                            </Group>
                            <Text size="xs" c="dimmed">{strategy.reason}</Text>
                            {(strategy.alternative_strategies ?? []).length > 0 && (
                              <Stack gap={4} mt="xs" pl="sm" style={{ borderLeft: '2px solid var(--mantine-color-default-border)' }}>
                                <Text size="xs" fw={500} c="dimmed">Alternatives</Text>
                                {(strategy.alternative_strategies ?? []).map((alt: any, j: number) => (
                                  <Group key={j} gap="xs" align="flex-start" wrap="wrap">
                                    <Badge color="grape" variant="light" size="xs" style={{ textTransform: 'capitalize' }}>
                                      {alt.approach.replace('_', ' ')}
                                    </Badge>
                                    {alt.target_total_kg != null && (
                                      <Badge color="blue" variant="light" size="xs">{alt.target_total_kg} kg</Badge>
                                    )}
                                    {alt.target_weight_class_kg != null && (
                                      <Badge color="teal" variant="light" size="xs">{alt.target_weight_class_kg} kg class</Badge>
                                    )}
                                    <Text size="xs" c="dimmed">{alt.reason}</Text>
                                  </Group>
                                ))}
                              </Stack>
                            )}
                          </Paper>
                        ))}
                      </Stack>
                    </Stack>
                  )}

                  {(weightClassStrategy.recommendation || weightClassStrategy.viable_options.length > 0) && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>Weight Class Strategy</Text>
                      <Paper withBorder p="sm">
                        {weightClassStrategy.recommended_weight_class_kg !== null && (
                          <Text size="sm" fw={500} mb={4}>
                            Recommended class: {weightClassStrategy.recommended_weight_class_kg} kg
                          </Text>
                        )}
                        <Text size="xs" c="dimmed">{weightClassStrategy.recommendation}</Text>
                        {weightClassStrategy.viable_options.length > 0 && (
                          <Stack gap={6} mt="sm">
                            {weightClassStrategy.viable_options.map((option, i) => (
                              <Group key={i} gap="sm" align="flex-start" wrap="nowrap">
                                <Badge color={WEIGHT_CLASS_COLORS[option.suitability] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize' }}>
                                  {option.weight_class_kg} kg • {option.suitability}
                                </Badge>
                                <Text size="xs" c="dimmed">{option.reason}</Text>
                              </Group>
                            ))}
                          </Stack>
                        )}
                      </Paper>
                    </Stack>
                  )}

                  <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                    {workingItems.length > 0 && (
                      <Stack gap="xs">
                        <Text size="sm" fw={500} c="green">What's Working</Text>
                        <Stack gap={4}>
                          {workingItems.map((item, i) => (
                            <Group key={i} gap="xs" align="flex-start" wrap="nowrap">
                              <Badge variant="light" color="green" size="sm">✓</Badge>
                              <Text size="xs">{item}</Text>
                            </Group>
                          ))}
                        </Stack>
                      </Stack>
                    )}
                    {blockedItems.length > 0 && (
                      <Stack gap="xs">
                        <Text size="sm" fw={500} c="red">Needs Attention</Text>
                        <Stack gap={4}>
                          {blockedItems.map((item, i) => (
                            <Group key={i} gap="xs" align="flex-start" wrap="nowrap">
                              <Badge variant="light" color="red" size="sm">✗</Badge>
                              <Text size="xs">{item}</Text>
                            </Group>
                          ))}
                        </Stack>
                      </Stack>
                    )}
                  </SimpleGrid>

                  {smallChanges.length > 0 && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>Suggested Adjustments</Text>
                      <Stack gap="xs">
                        {smallChanges.map((sc, i) => (
                          <Paper key={i} withBorder p="sm">
                            <Group gap="xs" mb={4}>
                              <Badge color={PRIORITY_COLORS[sc.priority] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize' }}>{sc.priority}</Badge>
                              <Text size="sm" fw={500}>{sc.change}</Text>
                            </Group>
                            <Text size="xs" c="dimmed">{sc.why}</Text>
                            {sc.risk && <Text size="xs" c="orange" mt={4}>Risk: {sc.risk}</Text>}
                          </Paper>
                        ))}
                      </Stack>
                    </Stack>
                  )}

                  {externalFactors.length > 0 && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>External Factors</Text>
                      <Stack gap="xs">
                        {externalFactors.map((factor, i) => (
                          <Paper key={i} withBorder p="sm">
                            <Group gap="xs" mb={4} wrap="wrap">
                              <Badge color={PRIORITY_COLORS[factor.impact] || 'gray'} variant="light" size="sm" style={{ textTransform: 'capitalize' }}>
                                {factor.impact}
                              </Badge>
                              <Text size="sm" fw={500}>{factor.factor}</Text>
                              {factor.separate_from_program && (
                                <Badge color="blue" variant="light" size="xs">External context</Badge>
                              )}
                            </Group>
                            <Text size="xs" c="dimmed">{factor.reason}</Text>
                          </Paper>
                        ))}
                      </Stack>
                    </Stack>
                  )}

                  {monitoringFocus.length > 0 && (
                    <Stack gap="xs">
                      <Text size="sm" fw={500}>Monitor Closely</Text>
                      <Group gap="xs" wrap="wrap">
                        {monitoringFocus.map((item, i) => (
                          <Badge key={i} color="blue" variant="light">{item}</Badge>
                        ))}
                      </Group>
                    </Stack>
                  )}

                  {evalReport.conclusion && (
                    <Text size="sm" fw={500} pt="sm" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>{evalReport.conclusion}</Text>
                  )}
                </Stack>
              )}
            </>
          ) : null}
        </Paper>
      )}
    </>
  );
}
