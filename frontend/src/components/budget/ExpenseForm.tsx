import { useEffect, useRef, useState } from 'react'
import { Camera, X, Check, Paperclip } from 'lucide-react'
import {
  ActionIcon, Badge, FileButton, Group, NumberInput, SegmentedControl, Select,
  SimpleGrid, Stack, Switch, Text, TextInput, Textarea, Tooltip,
} from '@mantine/core'
import { DatePickerInput, MonthPickerInput } from '@mantine/dates'
import type { BudgetItem, BudgetCategory, BudgetRecurrence, BudgetDatePrecision } from '@powerlifting/types'
import {
  COMP_LINK_CATEGORIES, defaultPriority, defaultRecurrence, nextPriority, todayIso,
} from './types'
import {
  CATEGORY_OPTIONS, RECURRENCE_OPTIONS, PRIORITY_STYLES,
} from './budgetConstants'
import {
  fromPickerValue, fromMonthPickerValue, toPickerValue, toMonthPickerValue,
} from './dateUtils'

export interface ExpenseFormProps {
  item: BudgetItem
  readOnly: boolean
  currency: string
  compOptions: { value: string; label: string }[]
  onChange: (patch: Partial<BudgetItem>) => void
  onSave: () => void
  onCancel: () => void
  isNew: boolean
  onPhotoUpload?: (file: File) => void
  onPhotoDelete?: () => void
  photoUrl?: string
}

export default function ExpenseForm({
  item, readOnly, currency, compOptions, onChange, onSave, onCancel, isNew,
  onPhotoUpload, onPhotoDelete, photoUrl,
}: ExpenseFormProps) {
  const nameRef = useRef<HTMLInputElement>(null)
  const [showNote, setShowNote] = useState<boolean>(Boolean(item.notes))
  const [showPhoto, setShowPhoto] = useState<boolean>(Boolean(item.photo_s3_key))

  useEffect(() => {
    if (isNew) nameRef.current?.focus()
  }, [isNew])

  const showCompLink = COMP_LINK_CATEGORIES.includes(item.category)

  const onCategoryChange = (value: string | null) => {
    const next = (value as BudgetCategory) ?? 'other'
    const compLinked = COMP_LINK_CATEGORIES.includes(next)
    const patch: Partial<BudgetItem> = { category: next, comp_linked: compLinked }
    const newRecurrence = defaultRecurrence(next)
    patch.recurrence = newRecurrence
    if (newRecurrence === 'ONE_TIME') {
      patch.date_precision = compLinked ? 'exact' : 'month'
    } else {
      patch.date_precision = 'month'
    }
    patch.priority_tier = defaultPriority(next, compLinked)
    if (!compLinked) patch.competition_id = null
    onChange(patch)
  }

  const onRecurrenceChange = (value: string | null) => {
    const next = (value as BudgetRecurrence) ?? 'ONE_TIME'
    const patch: Partial<BudgetItem> = { recurrence: next }
    if (next === 'ONE_TIME') {
      patch.date_precision = item.comp_linked ? 'exact' : 'month'
    } else {
      patch.date_precision = 'month'
    }
    onChange(patch)
  }

  const onPrecisionChange = (value: string) => {
    const precision = (value === 'exact' ? 'exact' : 'month') as BudgetDatePrecision
    const patch: Partial<BudgetItem> = { date_precision: precision }
    if (precision === 'month' && item.start_date && item.start_date.length === 10) {
      patch.start_date = item.start_date.slice(0, 7)
    } else if (precision === 'exact' && item.start_date && item.start_date.length === 7) {
      patch.start_date = `${item.start_date}-01`
    }
    onChange(patch)
  }

  const onPriorityCycle = () => {
    if (readOnly) return
    onChange({ priority_tier: nextPriority(item.priority_tier) })
  }

  const onCompLinkToggle = (checked: boolean) => {
    const patch: Partial<BudgetItem> = {
      comp_linked: checked,
      competition_id: checked ? item.competition_id : null,
    }
    if (checked && item.recurrence === 'ONE_TIME') patch.date_precision = 'exact'
    onChange(patch)
  }

  const onPurchasedToggle = (checked: boolean) => {
    onChange({
      purchased: checked,
      purchased_date: checked ? (item.purchased_date ?? todayIso()) : null,
    })
  }

  const onDateChange = (field: 'start_date' | 'end_date' | 'purchased_date') => (value: string | null) => {
    if (item.date_precision === 'month' && field !== 'purchased_date') {
      onChange({ [field]: fromMonthPickerValue(value) ?? undefined } as Partial<BudgetItem>)
    } else {
      onChange({ [field]: fromPickerValue(value) ?? undefined } as Partial<BudgetItem>)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'TEXTAREA') {
      e.preventDefault()
      onSave()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    }
  }

  const style = PRIORITY_STYLES[item.priority_tier]
  const dateLabel = item.recurrence === 'ONE_TIME'
    ? (item.date_precision === 'exact' ? 'Date' : 'Month')
    : 'Starts'

  return (
    <Stack gap="xs" onKeyDown={handleKeyDown}>
      <Group gap="xs" align="flex-end" wrap="nowrap">
        <TextInput
          ref={nameRef}
          placeholder="Expense name"
          value={item.name}
          onChange={(e) => onChange({ name: e.currentTarget.value })}
          disabled={readOnly}
          style={{ flex: 1, minWidth: 0 }}
          size="sm"
        />
        <Tooltip label={style.label} position="bottom">
          <Badge
            variant={style.variant}
            color={style.color}
            onClick={onPriorityCycle}
            style={{ cursor: readOnly ? 'default' : 'pointer', textTransform: 'none' }}
          >
            {style.label}
          </Badge>
        </Tooltip>
        {!readOnly && (
          <Group gap={4}>
            <ActionIcon variant="subtle" color="green" onClick={onSave} aria-label="Save">
              <Check size={16} />
            </ActionIcon>
            <ActionIcon variant="subtle" color="gray" onClick={onCancel} aria-label="Cancel">
              <X size={16} />
            </ActionIcon>
          </Group>
        )}
      </Group>

      <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="xs">
        <Select
          label="Category"
          size="xs"
          value={item.category}
          data={CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          onChange={onCategoryChange}
          disabled={readOnly}
          searchable
        />
        <Select
          label="Recurrence"
          size="xs"
          value={item.recurrence}
          data={RECURRENCE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          onChange={onRecurrenceChange}
          disabled={readOnly}
        />
        <NumberInput
          label={`Cost (${currency || 'CAD'})`}
          size="xs"
          value={item.cost}
          onChange={(v) => onChange({ cost: typeof v === 'number' ? v : 0 })}
          min={0}
          decimalScale={2}
          hideControls
          disabled={readOnly}
        />
        {item.recurrence === 'ONE_TIME' && (
          <SegmentedControl
            size="xs"
            fullWidth
            value={item.date_precision}
            onChange={onPrecisionChange}
            data={[
              { value: 'exact', label: 'Exact date' },
              { value: 'month', label: 'Month only' },
            ]}
            disabled={readOnly}
          />
        )}
      </SimpleGrid>

      <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="xs">
        {item.date_precision === 'month' && item.recurrence !== 'ONE_TIME' ? (
          <>
            <MonthPickerInput
              label={dateLabel}
              size="xs"
              valueFormat="MMM YYYY"
              value={toMonthPickerValue(item.start_date)}
              onChange={onDateChange('start_date')}
              disabled={readOnly}
              clearable
            />
            <MonthPickerInput
              label="Ends (blank = ongoing)"
              size="xs"
              valueFormat="MMM YYYY"
              value={toMonthPickerValue(item.end_date)}
              onChange={onDateChange('end_date')}
              disabled={readOnly}
              clearable
            />
          </>
        ) : item.date_precision === 'month' ? (
          <MonthPickerInput
            label="Month"
            size="xs"
            valueFormat="MMM YYYY"
            value={toMonthPickerValue(item.start_date)}
            onChange={onDateChange('start_date')}
            disabled={readOnly}
            clearable
          />
        ) : (
          <DatePickerInput
            label={dateLabel}
            size="xs"
            valueFormat="YYYY-MM-DD"
            value={toPickerValue(item.start_date)}
            onChange={onDateChange('start_date')}
            disabled={readOnly}
            clearable
          />
        )}
      </SimpleGrid>

      {showCompLink && (
        <Group gap="md" align="center" wrap="wrap">
          <Switch
            label="Tied to a competition?"
            checked={item.comp_linked}
            onChange={(e) => onCompLinkToggle(e.currentTarget.checked)}
            disabled={readOnly}
          />
          {item.comp_linked && (
            <Select
              size="xs"
              placeholder="Select competition"
              value={item.competition_id ?? ''}
              data={compOptions}
              onChange={(v) => onChange({ competition_id: v || null })}
              disabled={readOnly}
              clearable
              searchable
              style={{ flex: 1, minWidth: 160 }}
            />
          )}
        </Group>
      )}

      <Group gap="md" align="center" wrap="wrap">
        <Switch
          label="Purchased"
          checked={item.purchased}
          onChange={(e) => onPurchasedToggle(e.currentTarget.checked)}
          disabled={readOnly}
        />
        {item.purchased && (
          <DatePickerInput
            label="Purchased date"
            size="xs"
            valueFormat="YYYY-MM-DD"
            value={toPickerValue(item.purchased_date)}
            onChange={onDateChange('purchased_date')}
            disabled={readOnly}
            clearable
            w={180}
          />
        )}
      </Group>

      {!showNote && !readOnly && (
        <Text size="xs" c="dimmed" component="button" onClick={() => setShowNote(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left' }}>
          + Add note
        </Text>
      )}
      {showNote && (
        <Textarea
          label="Notes"
          size="xs"
          value={item.notes ?? ''}
          onChange={(e) => onChange({ notes: e.currentTarget.value || null })}
          disabled={readOnly}
          autosize
          minRows={1}
        />
      )}

      {!showPhoto && !readOnly && !item.photo_s3_key && (
        <Text size="xs" c="dimmed" component="button" onClick={() => setShowPhoto(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left' }}>
          <Group gap={4}><Paperclip size={12} /> Attach photo</Group>
        </Text>
      )}
      {showPhoto && (
        <Group gap="xs" align="center">
          <FileButton onChange={(f) => f && onPhotoUpload?.(f)} accept="image/*" disabled={readOnly}>
            {(props) => (
              <ActionIcon variant="light" {...props} disabled={readOnly} aria-label="Upload photo">
                <Camera size={16} />
              </ActionIcon>
            )}
          </FileButton>
          {photoUrl && <img src={photoUrl} alt="" style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 4 }} />}
          {item.photo_s3_key && !readOnly && onPhotoDelete && (
            <ActionIcon variant="subtle" color="red" onClick={onPhotoDelete} aria-label="Remove photo">
              <X size={14} />
            </ActionIcon>
          )}
        </Group>
      )}
    </Stack>
  )
}