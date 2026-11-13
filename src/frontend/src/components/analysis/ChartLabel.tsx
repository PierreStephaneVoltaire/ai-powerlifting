import { Tooltip } from '@mantine/core'
import { Info } from 'lucide-react'

export function ChartLabel({ text }: { text: string }) {
  return (
    <Tooltip label={text} withArrow multiline w={260} events={{ hover: true, focus: true, touch: true }}>
      <Info size={14} tabIndex={0} aria-label={text} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)', flexShrink: 0 }} />
    </Tooltip>
  )
}
