import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Box, Text, Group, Stack, ActionIcon, Tooltip } from '@mantine/core'
import { GripVertical, Trash2, Edit } from 'lucide-react'
import { Directive } from '../api/client'
import { TypeBadge } from './TypeBadge'

interface DirectiveCardProps {
  directive: Directive
  onEdit: (d: Directive) => void
  onDelete: (d: Directive) => void
  isDragging?: boolean
}

export function DirectiveCard({ directive, onEdit, onDelete, isDragging }: DirectiveCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging: isSortableDragging,
  } = useSortable({ id: `${directive.alpha}-${directive.beta}` })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isSortableDragging ? 0.4 : 1,
  }

  const isProtected = directive.alpha === 0 && directive.beta === 1

  return (
    <Box
      ref={setNodeRef}
      style={style}
      className={`
        bg-white dark:bg-[var(--bg-surface)]
        border border-[var(--tier-${directive.alpha}-border,--border-default)]
        rounded-lg p-3 shadow-sm
        ${isDragging ? 'shadow-xl ring-2 ring-violet-400' : ''}
      `}
    >
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Group gap={6} wrap="nowrap">
            <ActionIcon
              variant="subtle"
              color="gray"
              size="sm"
              style={{ cursor: 'grab', touchAction: 'none' }}
              {...attributes}
              {...listeners}
            >
              <GripVertical size={14} />
            </ActionIcon>
            <Text
              size="xs"
              fw={700}
              ff="'IBM Plex Mono', monospace"
              c="violet.6"
              style={{ lineHeight: 1.4 }}
            >
              {directive.alpha}-{directive.beta}
            </Text>
          </Group>
          <Group gap={4}>
            <Tooltip label="Edit">
              <ActionIcon
                variant="subtle"
                color="gray"
                size="sm"
                onClick={() => onEdit(directive)}
              >
                <Edit size={13} />
              </ActionIcon>
            </Tooltip>
            {!isProtected && (
              <Tooltip label="Delete">
                <ActionIcon
                  variant="subtle"
                  color="red"
                  size="sm"
                  onClick={() => onDelete(directive)}
                >
                  <Trash2 size={13} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>

        <Text size="sm" fw={600} lh={1.3}>
          {directive.label}
        </Text>

        <Text size="xs" c="dimmed" lh={1.5} lineClamp={2}>
          {directive.content}
        </Text>

        {directive.types && directive.types.length > 0 && (
          <Group gap={4} wrap="wrap">
            {directive.types.map(t => (
              <TypeBadge key={t} type={t} />
            ))}
          </Group>
        )}
      </Stack>
    </Box>
  )
}