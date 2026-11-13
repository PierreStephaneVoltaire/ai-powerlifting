import type { ReactNode } from 'react'
import { Anchor, Stack, Text } from '@mantine/core'

interface ChartHelpProps {
  description: ReactNode
  range?: ReactNode
  units?: ReactNode
  relation?: ReactNode
  formulaId?: string
  mb?: string
}

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Text fz="xs" c="dimmed">
      <Text span fz="xs" fw={600} c="dimmed">{label}: </Text>
      {children}
    </Text>
  )
}

export function ChartHelp({ description, range, units, relation, formulaId, mb = 'sm' }: ChartHelpProps) {
  return (
    <Stack gap={2} mb={mb}>
      <Text fz="xs" c="dimmed">
        {description}
        {formulaId && (
          <>
            {' '}
            <Anchor href={`#formula-${formulaId}`} fz="xs">Definition</Anchor>
          </>
        )}
      </Text>
      {range && <Line label="Expected">{range}</Line>}
      {units && <Line label="Units">{units}</Line>}
      {relation && <Line label="Relationship">{relation}</Line>}
    </Stack>
  )
}
