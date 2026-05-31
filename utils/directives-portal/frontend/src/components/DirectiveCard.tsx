import { Box, Text, Group, Stack, Badge, ActionIcon, Tooltip } from '@mantine/core'
import { Globe, Lock, Edit, Trash2, GripVertical, ArrowRightLeft, ChevronUp, ChevronDown } from 'lucide-react'
import { Directive } from '../api/client'
import { TypeBadge } from './TypeBadge'

const TIER_COLORS: Record<number, string> = {
  0: '#dc2626',
  1: '#ea580c',
  2: '#ca8a04',
  3: '#2563eb',
  4: '#0d9488',
  5: '#6b7280',
}

interface DirectiveCardProps {
  directive: Directive
  onEdit: (d: Directive) => void
  onDelete: (d: Directive) => void
  isOperator: boolean
  reorderMode?: boolean
  originalAlpha?: number
  originalBeta?: number
  dragHandleProps?: Record<string, unknown>
  canMove?: boolean
  onMoveTier?: (origAlpha: number, origBeta: number, direction: 'up' | 'down') => void
  currentAlpha?: number
}

export function DirectiveCard({
  directive,
  onEdit,
  onDelete,
  isOperator,
  reorderMode = false,
  originalAlpha,
  originalBeta,
  dragHandleProps,
  canMove = true,
  onMoveTier,
  currentAlpha,
}: DirectiveCardProps) {
  const tierColor = TIER_COLORS[directive.alpha] ?? '#6b7280'
  const isReadOnly = directive.read_only
  const canModify = !isReadOnly || isOperator
  const isProtected = directive.alpha === 0 && directive.beta === 1

  // Effective alpha for tier move buttons (use currentAlpha if in reorder mode, else directive.alpha)
  const effectiveAlpha = currentAlpha ?? directive.alpha
  const canMoveUp = canMove && effectiveAlpha > 0
  const canMoveDown = canMove && effectiveAlpha < 5

  // Detect if this directive has been swapped/repositioned
  const hasPositionChanged = reorderMode
    && originalAlpha !== undefined
    && originalBeta !== undefined
    && (originalAlpha !== directive.alpha || originalBeta !== directive.beta)

  // Detect if tier (alpha) changed specifically
  const tierChanged = reorderMode
    && originalAlpha !== undefined
    && originalAlpha !== directive.alpha

  return (
    <Box
      style={{
        background: hasPositionChanged
          ? 'var(--status-warning-bg)'
          : 'var(--bg-surface)',
        border: hasPositionChanged
          ? '0.5px solid var(--status-warning-border)'
          : `0.5px solid var(--tier-${directive.alpha}-border, var(--border-subtle))`,
        borderLeft: `3px solid ${tierColor}`,
        borderRadius: 'var(--border-radius-lg)',
        padding: 14,
        transition: 'background 120ms ease, border-color 120ms ease',
        cursor: reorderMode && canMove ? 'grab' : 'default',
        opacity: isReadOnly && !canMove ? 0.7 : isReadOnly ? 0.85 : 1,
      }}
    >
      <Stack gap={8}>
        {/* Header row: ID, swap indicator, global badge, actions */}
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Group gap={6} wrap="nowrap">
            {reorderMode && canMove && (
              <span {...dragHandleProps} style={{ cursor: 'grab', display: 'flex', alignItems: 'center', color: 'var(--color-text-secondary)' }}>
                <GripVertical size={14} />
              </span>
            )}
            {reorderMode && !canMove && (
              <Tooltip label="Global directive — only operator can move">
                <span style={{ display: 'flex', alignItems: 'center', color: 'var(--color-text-secondary)', opacity: 0.4 }}>
                  <Lock size={14} />
                </span>
              </Tooltip>
            )}
            <Text
              size="xs"
              fw={700}
              ff="'IBM Plex Mono', monospace"
              c={hasPositionChanged ? 'var(--status-warning-text)' : 'violet.6'}
              style={{ lineHeight: 1.4, textDecoration: hasPositionChanged ? 'line-through' : 'none' }}
            >
              {originalAlpha !== undefined && originalBeta !== undefined
                ? `${originalAlpha}-${originalBeta}`
                : `${directive.alpha}-${directive.beta}`}
            </Text>
            {hasPositionChanged && (
              <>
                <ArrowRightLeft size={12} style={{ color: 'var(--status-warning-text)', flexShrink: 0 }} />
                <Text
                  size="xs"
                  fw={700}
                  ff="'IBM Plex Mono', monospace"
                  c={tierChanged ? 'red' : 'orange'}
                  style={{ lineHeight: 1.4 }}
                >
                  {directive.alpha}-{directive.beta}
                </Text>
              </>
            )}
            {directive.global_directive && (
              <Tooltip label={isReadOnly ? 'Global directive (read-only)' : 'Global directive'}>
                <Badge
                  size="xs"
                  variant="light"
                  color="orange"
                  leftSection={<Globe size={10} />}
                  style={{ textTransform: 'lowercase' }}
                >
                  global
                </Badge>
              </Tooltip>
            )}
            {isReadOnly && (
              <Tooltip label="This directive is enforced globally and cannot be modified">
                <Badge
                  size="xs"
                  variant="light"
                  color="gray"
                  leftSection={<Lock size={10} />}
                  style={{ textTransform: 'lowercase' }}
                >
                  read-only
                </Badge>
              </Tooltip>
            )}
          </Group>
          <Group gap={4}>
            {/* Tier move arrows (upgrade/downgrade) in reorder mode */}
            {reorderMode && onMoveTier && originalAlpha !== undefined && originalBeta !== undefined && (
              <>
                <Tooltip label="Upgrade tier (higher priority)">
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    size="sm"
                    onClick={() => onMoveTier(originalAlpha, originalBeta, 'up')}
                    disabled={!canMoveUp}
                    style={{ opacity: canMoveUp ? 1 : 0.3 }}
                  >
                    <ChevronUp size={13} />
                  </ActionIcon>
                </Tooltip>
                <Tooltip label="Downgrade tier (lower priority)">
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    size="sm"
                    onClick={() => onMoveTier(originalAlpha, originalBeta, 'down')}
                    disabled={!canMoveDown}
                    style={{ opacity: canMoveDown ? 1 : 0.3 }}
                  >
                    <ChevronDown size={13} />
                  </ActionIcon>
                </Tooltip>
              </>
            )}
            {canModify && !isProtected && !reorderMode && (
              <>
                <Tooltip label="Edit">
                  <ActionIcon variant="subtle" color="gray" size="sm" onClick={() => onEdit(directive)}>
                    <Edit size={13} />
                  </ActionIcon>
                </Tooltip>
                <Tooltip label="Delete">
                  <ActionIcon variant="subtle" color="red" size="sm" onClick={() => onDelete(directive)}>
                    <Trash2 size={13} />
                  </ActionIcon>
                </Tooltip>
              </>
            )}
            {canModify && isProtected && !reorderMode && (
              <Tooltip label="Edit (protected)">
                <ActionIcon variant="subtle" color="gray" size="sm" onClick={() => onEdit(directive)}>
                  <Edit size={13} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>

        {/* Label */}
        <Text size="sm" fw={600} lh={1.3}>
          {directive.label}
        </Text>

        {/* Full content — no line clamping */}
        <Text size="xs" c="dimmed" lh={1.6} style={{ whiteSpace: 'pre-wrap' }}>
          {directive.content}
        </Text>

        {/* Type badges */}
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
