import { useState } from 'react'
import {
  ActionIcon, Badge, Box, Checkbox, Collapse, Group, Menu, Stack, Table, Text, Tooltip, UnstyledButton,
} from '@mantine/core'
import { Pencil, Trash2, Zap, MoreHorizontal, ChevronRight } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { BudgetItem } from './types'
import {
  PRIORITY_STYLES, categoryIcon, recurrenceIcon, CATEGORY_OPTIONS,
} from './budgetConstants'
import { datePeriodLabel, formatCost, recurrenceCostSuffix } from './dateUtils'
import ExpenseForm from './ExpenseForm'

export interface ExpenseRowProps {
  item: BudgetItem
  readOnly: boolean
  currency: string
  compOptions: { value: string; label: string }[]
  isEditing: boolean
  isNew: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSave: () => void
  onChange: (patch: Partial<BudgetItem>) => void
  onCyclePriority: () => void
  onTogglePurchased: (purchased: boolean) => void
  onDelete: () => void
  onPhotoUpload?: (file: File) => void
  onPhotoDelete?: () => void
  photoUrl?: string
  isMobile: boolean
}

export default function ExpenseRow({
  item, readOnly, currency, compOptions, isEditing, isNew,
  onStartEdit, onCancelEdit, onSave, onChange, onCyclePriority,
  onTogglePurchased, onDelete, onPhotoUpload, onPhotoDelete, photoUrl, isMobile,
}: ExpenseRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const style = PRIORITY_STYLES[item.priority_tier]
  const Icon: LucideIcon = categoryIcon(item.category)
  const RecurrenceIcon: LucideIcon = recurrenceIcon(item.recurrence)
  const compName = item.comp_linked
    ? compOptions.find((c) => c.value === item.competition_id)?.label ?? ''
    : ''
  const periodLabel = datePeriodLabel(item)
  const suffix = recurrenceCostSuffix(item.recurrence)
  const costLabel = formatCost(item.cost, currency, item.recurrence)
  const cut = (item as BudgetItem & { cut_by_ai?: boolean }).cut_by_ai

  if (isEditing) {
    return (
      <Box py="xs" px="sm" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
        <ExpenseForm
          item={item}
          readOnly={readOnly}
          currency={currency}
          compOptions={compOptions}
          onChange={onChange}
          onSave={onSave}
          onCancel={onCancelEdit}
          isNew={isNew}
          onPhotoUpload={onPhotoUpload}
          onPhotoDelete={onPhotoDelete}
          photoUrl={photoUrl}
        />
      </Box>
    )
  }

  if (isMobile) {
    return (
      <>
        <Group gap="sm" align="center" wrap="nowrap" py="xs" px="sm" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
          {readOnly ? (
            <Badge variant={style.variant} color={style.color} style={{ textTransform: 'none', minWidth: 64, justifyContent: 'center' }}>{style.label}</Badge>
          ) : (
            <Badge
              variant={style.variant}
              color={style.color}
              onClick={onCyclePriority}
              style={{ cursor: 'pointer', textTransform: 'none', minWidth: 64, justifyContent: 'center' }}
            >
              {style.label}
            </Badge>
          )}
          <UnstyledButton
            onClick={() => setExpanded((e) => !e)}
            style={{ flex: 1, minWidth: 0, textAlign: 'left' }}
          >
            <Stack gap={2}>
              <Group gap={4} wrap="nowrap">
                <Text size="sm" fw={500} truncate style={{ textDecoration: cut ? 'line-through' : undefined, color: item.purchased ? 'var(--mantine-color-dimmed)' : undefined }}>
                  {item.name || 'Untitled'}
                </Text>
                {item.comp_linked && (
                  <Tooltip label={compName || 'Competition linked'} position="top">
                    <Zap size={12} color="var(--mantine-color-yellow-6)" style={{ flexShrink: 0 }} />
                  </Tooltip>
                )}
              </Group>
              <Group gap={6} wrap="nowrap">
                <Icon size={12} color="var(--mantine-color-dimmed)" />
                <Text size="xs" c="dimmed">{periodLabel}</Text>
                <RecurrenceIcon size={12} color="var(--mantine-color-dimmed)" />
              </Group>
            </Stack>
          </UnstyledButton>
          <Group gap={6} align="center" wrap="nowrap">
            <Checkbox
              checked={item.purchased}
              onChange={(e) => onTogglePurchased(e.currentTarget.checked)}
              disabled={readOnly}
              size="sm"
              aria-label="Purchased"
            />
            <ActionIcon variant="subtle" size="sm" onClick={() => setExpanded((e) => !e)} aria-label="Expand">
              <ChevronRight size={14} style={{ transform: expanded ? 'rotate(90deg)' : undefined, transition: 'transform 0.15s' }} />
            </ActionIcon>
          </Group>
        </Group>
        <Collapse expanded={expanded}>
          <Box py="sm" px="sm" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
            <ExpenseForm
              item={item}
              readOnly={readOnly}
              currency={currency}
              compOptions={compOptions}
              onChange={onChange}
              onSave={() => { setExpanded(false) }}
              onCancel={() => setExpanded(false)}
              isNew={false}
              onPhotoUpload={onPhotoUpload}
              onPhotoDelete={onPhotoDelete}
              photoUrl={photoUrl}
            />
          </Box>
        </Collapse>
      </>
    )
  }

  return (
    <>
      <Table.Tr style={{ background: expanded ? 'var(--mantine-color-gray-0)' : undefined }}>
        <Table.Td style={{ width: 28 }}>
          {!readOnly && (
            <ActionIcon variant="subtle" size="sm" onClick={() => setExpanded((e) => !e)} aria-label="Expand row">
              <ChevronRight size={14} style={{ transform: expanded ? 'rotate(90deg)' : undefined, transition: 'transform 0.15s' }} />
            </ActionIcon>
          )}
        </Table.Td>
        <Table.Td style={{ width: 90 }}>
          <Badge
            variant={style.variant}
            color={style.color}
            onClick={onCyclePriority}
            style={{ cursor: readOnly ? 'default' : 'pointer', textTransform: 'none', minWidth: 64, justifyContent: 'center' }}
          >
            {style.label}
          </Badge>
        </Table.Td>
        <Table.Td style={{ width: 36 }}>
          <Tooltip label={CATEGORY_OPTIONS.find((c) => c.value === item.category)?.label ?? item.category} position="top">
            <Icon size={16} color="var(--mantine-color-dimmed)" />
          </Tooltip>
        </Table.Td>
        <Table.Td>
          <Group gap={4} wrap="nowrap">
            <Text size="sm" truncate style={{ maxWidth: 200, textDecoration: cut ? 'line-through' : undefined, color: item.purchased ? 'var(--mantine-color-dimmed)' : undefined }}>
              {item.name || 'Untitled'}
            </Text>
            {item.comp_linked && (
              <Tooltip label={compName || 'Competition linked'} position="top">
                <Zap size={12} color="var(--mantine-color-yellow-6)" />
              </Tooltip>
            )}
          </Group>
        </Table.Td>
        <Table.Td style={{ width: 28 }}>
          <Tooltip label={item.recurrence} position="top">
            <RecurrenceIcon size={14} color="var(--mantine-color-dimmed)" />
          </Tooltip>
        </Table.Td>
        <Table.Td ta="right" style={{ whiteSpace: 'nowrap' }}>{costLabel}</Table.Td>
        <Table.Td style={{ whiteSpace: 'nowrap' }}>
          <Text size="xs" c="dimmed">{periodLabel}</Text>
        </Table.Td>
        <Table.Td style={{ width: 28 }}>
          {item.comp_linked && (
            <Tooltip label={compName || 'Competition linked'} position="top">
              <Zap size={12} color="var(--mantine-color-yellow-6)" />
            </Tooltip>
          )}
        </Table.Td>
        <Table.Td style={{ width: 40 }}>
          <Checkbox
            checked={item.purchased}
            onChange={(e) => onTogglePurchased(e.currentTarget.checked)}
            disabled={readOnly}
            aria-label="Purchased"
          />
        </Table.Td>
        <Table.Td style={{ width: 40 }}>
          {!readOnly && (
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <ActionIcon variant="subtle" size="sm" aria-label="Actions">
                  <MoreHorizontal size={16} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<Pencil size={14} />} onClick={() => { setExpanded(true); onStartEdit() }}>
                  Edit
                </Menu.Item>
                <Menu.Item
                  leftSection={<Trash2 size={14} />}
                  color="red"
                  onClick={() => {
                    if (confirmDelete) {
                      onDelete()
                    } else {
                      setConfirmDelete(true)
                      setTimeout(() => setConfirmDelete(false), 3000)
                    }
                  }}
                >
                  {confirmDelete ? `Delete '${item.name || 'this'}'?` : 'Delete'}
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          )}
        </Table.Td>
      </Table.Tr>
      {expanded && (
        <Table.Tr>
          <Table.Td colSpan={10} p="md" style={{ background: 'var(--mantine-color-gray-0)' }}>
            <ExpenseForm
              item={item}
              readOnly={readOnly}
              currency={currency}
              compOptions={compOptions}
              onChange={onChange}
              onSave={() => setExpanded(false)}
              onCancel={() => setExpanded(false)}
              isNew={false}
              onPhotoUpload={onPhotoUpload}
              onPhotoDelete={onPhotoDelete}
              photoUrl={photoUrl}
            />
          </Table.Td>
        </Table.Tr>
      )}
    </>
  )
}