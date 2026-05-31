import { Badge } from '@mantine/core'

const TYPE_COLORS: Record<string, string> = {
  core: 'red',
  code: 'blue',
  health: 'green',
  finance: 'teal',
  memory: 'violet',
  security: 'orange',
  architecture: 'cyan',
  style: 'pink',
  tool: 'grape',
  metacognition: 'indigo',
}

interface TypeBadgeProps {
  type: string
}

export function TypeBadge({ type }: TypeBadgeProps) {
  const color = TYPE_COLORS[type] ?? 'gray'
  return (
    <Badge
      size="xs"
      variant="light"
      color={color}
      style={{ textTransform: 'lowercase', fontFamily: "'IBM Plex Mono', monospace" }}
    >
      {type}
    </Badge>
  )
}