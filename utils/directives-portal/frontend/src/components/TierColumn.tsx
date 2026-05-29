import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Box, Text, Stack, Group } from '@mantine/core'
import { Directive } from '../api/client'
import { DirectiveCard } from './DirectiveCard'

const TIER_META: Record<number, { label: string; description: string; color: string }> = {
  0: { label: 'Tier 0', description: 'Fundamental — Never break', color: '#dc2626' },
  1: { label: 'Tier 1', description: 'Critical — Only bypass with explicit request', color: '#ea580c' },
  2: { label: 'Tier 2', description: 'Standard — Recommended', color: '#ca8a04' },
  3: { label: 'Tier 3', description: 'Preference — Optional but encouraged', color: '#2563eb' },
  4: { label: 'Tier 4', description: 'Advisory — Consider', color: '#0d9488' },
  5: { label: 'Tier 5', description: 'Notes — Background context', color: '#6b7280' },
}

interface TierColumnProps {
  alpha: number
  directives: Directive[]
  onEdit: (d: Directive) => void
  onDelete: (d: Directive) => void
}

export function TierColumn({ alpha, directives, onEdit, onDelete }: TierColumnProps) {
  const meta = TIER_META[alpha] ?? { label: `Tier ${alpha}`, description: '', color: '#6b7280' }
  const ids = directives.map(d => `${d.alpha}-${d.beta}`)

  const { setNodeRef, isOver } = useDroppable({ id: `tier-${alpha}` })

  return (
    <Box
      ref={setNodeRef}
      style={{
        width: 260,
        minWidth: 260,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Column header */}
      <Box
        style={{
          background: `var(--tier-${alpha}-bg, var(--bg-elevated))`,
          border: `2px solid ${isOver ? meta.color : `var(--tier-${alpha}-border, var(--border-default))`}`,
          borderBottom: 'none',
          borderRadius: '8px 8px 0 0',
          padding: '10px 12px',
          transition: 'border-color 150ms',
        }}
      >
        <Group justify="space-between" align="center">
          <Group gap={8}>
            <Box
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: meta.color,
                flexShrink: 0,
              }}
            />
            <Text fw={700} size="sm" style={{ fontFamily: "'Barlow Condensed', sans-serif" }}>
              {meta.label}
            </Text>
          </Group>
          <Text size="xs" c="dimmed" fw={500}>
            {directives.length}
          </Text>
        </Group>
        <Text size="xs" c="dimmed" mt={2}>
          {meta.description}
        </Text>
      </Box>

      {/* Cards */}
      <Box
        style={{
          flex: 1,
          background: `var(--tier-${alpha}-bg, var(--bg-elevated))`,
          border: `2px solid ${isOver ? meta.color : `var(--tier-${alpha}-border, var(--border-default))`}`,
          borderRadius: '0 0 8px 8px',
          padding: 8,
          minHeight: 120,
          transition: 'border-color 150ms',
        }}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <Stack gap={6}>
            {directives.map(d => (
              <DirectiveCard
                key={`${d.alpha}-${d.beta}`}
                directive={d}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
            {directives.length === 0 && (
              <Box
                style={{
                  border: '2px dashed var(--border-default)',
                  borderRadius: 8,
                  padding: '20px 12px',
                  textAlign: 'center',
                }}
              >
                <Text size="xs" c="dimmed">
                  Drop here
                </Text>
              </Box>
            )}
          </Stack>
        </SortableContext>
      </Box>
    </Box>
  )
}