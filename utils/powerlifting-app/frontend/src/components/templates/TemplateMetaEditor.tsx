import { Stack, TextInput, Textarea } from '@mantine/core'
import type { TemplateMeta } from '@powerlifting/types'

interface Props {
  meta: TemplateMeta
  onChange: (meta: TemplateMeta) => void
}

export function TemplateMetaEditor({ meta, onChange }: Props) {
  return (
    <Stack gap="md">
      <TextInput
        label="Name"
        value={meta.name}
        onChange={(e) => onChange({ ...meta, name: e.currentTarget.value })}
      />
      <Textarea
        label="Description"
        value={meta.description}
        onChange={(e) => onChange({ ...meta, description: e.currentTarget.value })}
        autosize
        minRows={2}
      />
      <TextInput
        type="number"
        label="Estimated Weeks"
        value={meta.estimated_weeks}
        onChange={(e) => onChange({ ...meta, estimated_weeks: Number(e.currentTarget.value) || 1 })}
      />
      <TextInput
        type="number"
        label="Days Per Week"
        value={meta.days_per_week}
        onChange={(e) => onChange({ ...meta, days_per_week: Number(e.currentTarget.value) || 1 })}
      />
    </Stack>
  )
}
