import { Accordion, Anchor, Badge, Box, Group, Paper, Stack, Text } from '@mantine/core'
import { AlertTriangle } from 'lucide-react'
import type { AnalyticsAlert } from '@/api/analytics'

const SEVERITY_META: Record<AnalyticsAlert['severity'], { color: string; label: string }> = {
  warning: { color: 'red', label: 'Warning' },
  caution: { color: 'yellow', label: 'Caution' },
  info: { color: 'blue', label: 'Info' },
}

const SOURCE_LABELS: Record<AnalyticsAlert['source'], string> = {
  acwr: 'ACWR',
  fatigue: 'Fatigue',
  readiness: 'Readiness',
  projection: 'Projection',
  specificity: 'Specificity',
  banister: 'Banister',
  decoupling: 'Decoupling',
  monotony: 'Monotony',
}

const SOURCE_FORMULAS: Partial<Record<AnalyticsAlert['source'], string>> = {
  acwr: 'acwr',
  fatigue: 'fatigue_index',
  readiness: 'readiness_score',
  projection: 'competition_projection',
  specificity: 'specificity_ratio',
  banister: 'banister_ffm',
  decoupling: 'decoupling',
  monotony: 'monotony_strain',
}

interface AlertsStripProps {
  alerts: AnalyticsAlert[]
}

export function AlertsStrip({ alerts }: AlertsStripProps) {
  if (!alerts.length) return null

  return (
    <Paper
      withBorder
      p="md"
      className="if-card"
      style={{ borderColor: 'var(--status-info-border)' }}
    >
      <Group gap="xs" mb="sm">
        <AlertTriangle size={18} />
        <Text fw={600} c="var(--text-primary)">Coaching Alerts</Text>
        <span className="if-pill if-pill-info">{alerts.length}</span>
      </Group>
      <Text fz="sm" c="dimmed" mb="md">
        Deterministic coaching-language summaries derived from the analysis response.
      </Text>

      <Accordion multiple variant="separated">
        {alerts.map((alert, index) => {
          const severity = SEVERITY_META[alert.severity]
          const formulaId = SOURCE_FORMULAS[alert.source]
          return (
            <Accordion.Item key={`${alert.source}-${index}`} value={`${alert.source}-${index}`}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <Stack gap={4} style={{ flex: 1 }}>
                    <Group gap="xs" wrap="wrap">
                      <Badge variant="light" color={severity.color} size="sm">{severity.label}</Badge>
                      <span className="if-pill if-pill-neutral">{SOURCE_LABELS[alert.source]}</span>
                    </Group>
                    <Text fw={600} fz="sm">
                      {alert.message}
                    </Text>
                  </Stack>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  <Box
                    component="pre"
                    fz="xs"
                    p="sm"
                    style={{
                      margin: 0,
                      borderRadius: 'var(--mantine-radius-sm)',
                      background: 'var(--mantine-color-default-hover)',
                      fontFamily: 'monospace',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {alert.raw_detail}
                  </Box>
                  {formulaId && (
                    <Anchor href={`#formula-${formulaId}`} fz="sm" fw={600}>
                      Open formula reference
                    </Anchor>
                  )}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          )
        })}
      </Accordion>
    </Paper>
  )
}
