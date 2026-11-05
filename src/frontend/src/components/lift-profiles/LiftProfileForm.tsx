import { useState } from 'react'
import { Alert, Button, Group, Paper, Radio, SimpleGrid, Stack, Text, Textarea } from '@mantine/core'
import { Sparkles } from 'lucide-react'
import type { LiftProfile } from '@powerlifting/types'
import { suggestLiftProfile } from '@/api/client'
import { cleanOptions, liftProfileFields, lockedValue, missingOptions, VOLUME_TOLERANCE_FIELD, type LiftProfileField } from '@/utils/liftProfile'

interface Props {
  profile: LiftProfile
  onChange: (profile: LiftProfile) => void
  readOnly?: boolean
}

function OptionGroup({ field, value, locked, highlighted, disabled, onSelect }: {
  field: LiftProfileField
  value: string | undefined
  locked: string | null
  highlighted: boolean
  disabled: boolean
  onSelect: (value: string) => void
}) {
  return (
    <Radio.Group
      label={field.label}
      description={locked ? 'Set by your stance' : undefined}
      value={locked ?? value ?? null}
      onChange={onSelect}
      styles={highlighted ? { label: { color: 'var(--mantine-color-blue-6)' } } : undefined}
    >
      <Group gap="sm" mt={6}>
        {field.options.map((option) => (
          <Radio key={option.value} value={option.value} label={option.label} disabled={disabled || Boolean(locked)} />
        ))}
      </Group>
    </Radio.Group>
  )
}

export function LiftProfileForm({ profile, onChange, readOnly = false }: Props) {
  const [description, setDescription] = useState('')
  const [suggesting, setSuggesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [changed, setChanged] = useState<string[]>([])
  const options = profile.options ?? {}
  const fields = liftProfileFields(profile.lift)
  const missing = missingOptions(profile)

  const select = (key: string, value: string) => {
    setChanged((current) => current.filter((item) => item !== key))
    onChange({ ...profile, options: cleanOptions(profile.lift, { ...options, [key]: value }) })
  }

  const suggest = async () => {
    setSuggesting(true)
    setError(null)
    try {
      const result = await suggestLiftProfile(profile.lift, description, profile)
      onChange({ ...profile, options: cleanOptions(profile.lift, result.options), volume_tolerance: result.volume_tolerance ?? profile.volume_tolerance })
      setChanged(result.changed)
    } catch (err: any) {
      setError(err?.message ?? 'The helper could not pick options')
    } finally {
      setSuggesting(false)
    }
  }

  return (
    <Stack gap="lg">
      <Paper withBorder p="md">
        <Stack gap="xs">
          <Text fw={600}>Describe your {profile.lift}</Text>
          <Text size="xs" c="dimmed">Optional. Write it however you like and the helper picks the matching options below. You can change any of them before saving.</Text>
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.currentTarget.value)}
            placeholder={profile.lift === 'bench' ? 'e.g. wide grip, big arch, touch low on the chest, I stall halfway up' : profile.lift === 'squat' ? 'e.g. low bar, shoulder width, slight toe out, I grind out of the hole' : 'e.g. conventional, hook grip, I wedge in and it slows below the knee'}
            autosize
            minRows={2}
            maxLength={2000}
            disabled={readOnly || suggesting}
          />
          <Group justify="flex-end">
            <Button variant="light" leftSection={<Sparkles size={16} />} onClick={suggest} loading={suggesting} disabled={readOnly || !description.trim()}>
              Pick options for me
            </Button>
          </Group>
          {error && <Alert color="red" variant="light">{error}</Alert>}
          {changed.length > 0 && <Text size="xs" c="blue">Updated {changed.length} option{changed.length === 1 ? '' : 's'} from your description (highlighted). Review them before saving.</Text>}
        </Stack>
      </Paper>

      <Paper withBorder p="md">
        <Stack gap="md">
          <Group justify="space-between">
            <Text fw={600}>Technique</Text>
            <Text size="xs" c={missing.length ? 'yellow' : 'green'}>{missing.length ? `${missing.length} left to choose` : 'All chosen'}</Text>
          </Group>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" verticalSpacing="lg">
            {fields.map((field) => (
              <OptionGroup
                key={field.key}
                field={field}
                value={options[field.key]}
                locked={lockedValue(field, options)}
                highlighted={changed.includes(field.key)}
                disabled={readOnly}
                onSelect={(value) => select(field.key, value)}
              />
            ))}
          </SimpleGrid>
        </Stack>
      </Paper>

      <Paper withBorder p="md">
        <Stack gap="md">
          <OptionGroup
            field={VOLUME_TOLERANCE_FIELD}
            value={profile.volume_tolerance}
            locked={null}
            highlighted={false}
            disabled={readOnly}
            onSelect={(value) => onChange({ ...profile, volume_tolerance: value as LiftProfile['volume_tolerance'] })}
          />
          <Textarea
            label="Notes"
            description="Optional"
            value={profile.notes ?? ''}
            onChange={(event) => onChange({ ...profile, notes: event.currentTarget.value })}
            autosize
            minRows={2}
            maxLength={1000}
            disabled={readOnly}
          />
        </Stack>
      </Paper>
    </Stack>
  )
}
