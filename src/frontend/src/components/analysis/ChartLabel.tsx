import { Anchor, Group, Text } from '@mantine/core'
import { Info } from 'lucide-react'

interface ChartLabelProps {
  text: string
  formulaId: string
  mb?: string
}

export function ChartLabel({ text, formulaId, mb = 'xs' }: ChartLabelProps) {
  return (
    <Group gap={4} mb={mb} wrap="nowrap">
      <Text fz="xs" c="dimmed">{text}</Text>
      <Anchor href={`#formula-${formulaId}`} aria-label="Formula definition" lh={1}>
        <Info size={12} />
      </Anchor>
    </Group>
  )
}
