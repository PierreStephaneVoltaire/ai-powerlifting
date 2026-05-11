import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Archive, Plus, Save, Shield } from 'lucide-react'
import {
  Accordion,
  Badge,
  Button,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import type {
  FederationLibrary,
  FederationRecord,
  QualificationStandard,
} from '@powerlifting/types'
import { useFederationStore } from '@/store/federationStore'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'

const SEX_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]

const EQUIPMENT_OPTIONS = [
  { value: 'raw', label: 'Raw' },
  { value: 'wraps', label: 'Wraps' },
  { value: 'single-ply', label: 'Single-ply' },
  { value: 'multi-ply', label: 'Multi-ply' },
]

const EVENT_OPTIONS = [
  { value: 'sbd', label: 'SBD' },
  { value: 'bench-only', label: 'Bench Only' },
  { value: 'deadlift-only', label: 'Deadlift Only' },
]

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
]

function cloneLibrary(library: FederationLibrary | null): FederationLibrary | null {
  if (!library) return null
  return JSON.parse(JSON.stringify(library)) as FederationLibrary
}

function makeFederation(): FederationRecord {
  const now = new Date().toISOString()
  return {
    id: crypto.randomUUID(),
    name: 'New Federation',
    abbreviation: '',
    region: '',
    notes: '',
    status: 'active',
    created_at: now,
    updated_at: now,
  }
}

function makeStandard(): QualificationStandard {
  return {
    id: crypto.randomUUID(),
    federation_id: '',
    season_year: new Date().getFullYear(),
    sex: 'male',
    equipment: 'raw',
    event: 'sbd',
    weight_class_kg: 83,
    required_total_kg: 0,
    source_type: 'user_entered',
    status: 'active',
    updated_at: new Date().toISOString(),
  }
}

function federationStatusColor(status: FederationRecord['status']): string {
  return status === 'active' ? 'blue' : 'gray'
}

function standardStatusColor(status: QualificationStandard['status']): string {
  return status === 'active' ? 'green' : 'gray'
}

export default function FederationsPage() {
  const { library, loadLibrary, saveLibrary } = useFederationStore()
  const { program } = useProgramStore()
  const { pushToast } = useUiStore()
  const [draft, setDraft] = useState<FederationLibrary | null>(null)
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    loadLibrary().catch(console.error)
  }, [loadLibrary])

  useEffect(() => {
    if (!library) return
    setDraft(cloneLibrary(library))
    setHasChanges(false)
  }, [library])

  const referencedFederationIds = useMemo(() => {
    const ids = new Set<string>()
    const standardsById = new Map((library?.qualification_standards ?? []).map(item => [item.id, item.federation_id]))
    for (const goal of program?.goals ?? []) {
      if (goal.target_federation_id) ids.add(goal.target_federation_id)
      if (goal.target_standard_id && standardsById.has(goal.target_standard_id)) {
        ids.add(standardsById.get(goal.target_standard_id) as string)
      }
      for (const standardId of goal.target_standard_ids ?? []) {
        if (standardsById.has(standardId)) ids.add(standardsById.get(standardId) as string)
      }
    }
    for (const competition of program?.competitions ?? []) {
      if (competition.federation_id) ids.add(competition.federation_id)
      for (const federationId of competition.counts_toward_federation_ids ?? []) {
        ids.add(federationId)
      }
    }
    return ids
  }, [library?.qualification_standards, program?.competitions, program?.goals])

  const referencedStandardIds = useMemo(() => {
    const ids = new Set<string>()
    for (const goal of program?.goals ?? []) {
      if (goal.target_standard_id) ids.add(goal.target_standard_id)
      for (const standardId of goal.target_standard_ids ?? []) {
        ids.add(standardId)
      }
    }
    return ids
  }, [program?.goals])

  function updateDraft(patch: Partial<FederationLibrary>) {
    setDraft(current => (current ? { ...current, ...patch } : current))
    setHasChanges(true)
  }

  function updateFederation(federationId: string, patch: Partial<FederationRecord>) {
    if (!draft) return
    updateDraft({
      federations: draft.federations.map(item => (
        item.id === federationId
          ? { ...item, ...patch, updated_at: new Date().toISOString() }
          : item
      )),
    })
  }

  function updateStandard(standardId: string, patch: Partial<QualificationStandard>) {
    if (!draft) return
    updateDraft({
      qualification_standards: draft.qualification_standards.map(item => (
        item.id === standardId
          ? { ...item, ...patch, updated_at: new Date().toISOString() }
          : item
      )),
    })
  }

  function addFederation() {
    if (!draft) return
    updateDraft({
      federations: [...draft.federations, makeFederation()],
    })
  }

  function addStandard() {
    if (!draft) return
    if (draft.federations.length === 0) {
      pushToast({ message: 'Add a federation before adding standards', type: 'error' })
      return
    }
    const standard = makeStandard()
    standard.federation_id = draft.federations[0].id
    updateDraft({
      qualification_standards: [...draft.qualification_standards, standard],
    })
  }

  async function handleSave() {
    if (!draft) return
    try {
      await saveLibrary(draft)
      setHasChanges(false)
      pushToast({ message: 'Federation library saved', type: 'success' })
    } catch (error) {
      pushToast({ message: 'Failed to save federation library', type: 'error' })
    }
  }

  const federationOptions = (draft?.federations ?? []).map(item => ({
    value: item.id,
    label: item.abbreviation ? `${item.abbreviation} • ${item.name}` : item.name,
  }))

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
              Designer
            </Text>
            <Text c="dimmed">/</Text>
            <Title order={2}>Federations</Title>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>
            Reusable athlete-wide library of federations and manually maintained qualification standards.
          </Text>
        </Stack>
        <Group gap="sm">
          {hasChanges && (
            <Button leftSection={<Save size={16} />} onClick={handleSave}>
              Save
            </Button>
          )}
          <Button variant="default" leftSection={<Plus size={16} />} onClick={addFederation}>
            Add Federation
          </Button>
          <Button variant="default" leftSection={<Plus size={16} />} onClick={addStandard}>
            Add Standard
          </Button>
        </Group>
      </Group>

      {!draft ? (
        <Paper withBorder p="xl">
          <Group justify="center">
            <Text c="dimmed">Loading federation library...</Text>
          </Group>
        </Paper>
      ) : (
        <>
          <Paper withBorder p="md">
            <Text size="sm" c="dimmed">
              These records are shared across your programs. Archive old standards instead of deleting them so linked goals and competitions keep historical context.
            </Text>
          </Paper>

          <Stack gap="sm">
            <Group gap="xs">
              <Shield size={18} />
              <Text fw={600}>Federations</Text>
            </Group>
            {draft.federations.length === 0 ? (
              <Paper withBorder p="lg">
                <Text size="sm" c="dimmed">No federations yet. Add one to start building standards.</Text>
              </Paper>
            ) : (
              <Accordion variant="separated">
                {draft.federations.map(item => (
                  <Accordion.Item key={item.id} value={item.id}>
                    <Accordion.Control>
                      <Group gap="sm" wrap="nowrap">
                        <Badge variant="light" color={federationStatusColor(item.status)}>
                          {item.status}
                        </Badge>
                        <Stack gap={0}>
                          <Text fw={500}>{item.abbreviation || item.name}</Text>
                          <Text size="xs" c="dimmed">{item.name}</Text>
                        </Stack>
                      </Group>
                    </Accordion.Control>
                    <Accordion.Panel>
                      <Stack gap="md">
                        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                          <TextInput
                            label="Name"
                            value={item.name}
                            onChange={(event) => updateFederation(item.id, { name: event.currentTarget.value })}
                          />
                          <TextInput
                            label="Abbreviation"
                            value={item.abbreviation || ''}
                            onChange={(event) => updateFederation(item.id, { abbreviation: event.currentTarget.value })}
                          />
                          <TextInput
                            label="Region"
                            value={item.region || ''}
                            onChange={(event) => updateFederation(item.id, { region: event.currentTarget.value })}
                          />
                          <Select
                            label="Status"
                            data={STATUS_OPTIONS}
                            value={item.status}
                            onChange={(value) => value && updateFederation(item.id, { status: value as FederationRecord['status'] })}
                          />
                        </SimpleGrid>
                        <Textarea
                          label="Notes"
                          autosize
                          minRows={2}
                          value={item.notes || ''}
                          onChange={(event) => updateFederation(item.id, { notes: event.currentTarget.value })}
                        />
                        <Group justify="space-between">
                          <Text size="xs" c="dimmed">
                            {referencedFederationIds.has(item.id) ? 'Referenced by the current program.' : 'Not referenced by the current program.'}
                          </Text>
                          <Button
                            variant="light"
                            color={item.status === 'active' ? 'gray' : 'blue'}
                            leftSection={<Archive size={14} />}
                            onClick={() => updateFederation(item.id, {
                              status: item.status === 'active' ? 'archived' : 'active',
                            })}
                          >
                            {item.status === 'active' ? 'Archive' : 'Restore'}
                          </Button>
                        </Group>
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                ))}
              </Accordion>
            )}
          </Stack>

          <Stack gap="sm">
            <Group gap="xs">
              <Shield size={18} />
              <Text fw={600}>Qualification Standards</Text>
            </Group>
            {draft.qualification_standards.length === 0 ? (
              <Paper withBorder p="lg">
                <Text size="sm" c="dimmed">No standards yet. Add the totals you care about and link them from goals or competitions.</Text>
              </Paper>
            ) : (
              <Accordion variant="separated">
                {draft.qualification_standards
                  .slice()
                  .sort((a, b) => {
                    if (a.season_year !== b.season_year) return b.season_year - a.season_year
                    return a.weight_class_kg - b.weight_class_kg
                  })
                  .map(item => {
                    const federation = draft.federations.find(fed => fed.id === item.federation_id)
                    return (
                      <Accordion.Item key={item.id} value={item.id}>
                        <Accordion.Control>
                          <Group gap="sm" wrap="nowrap">
                            <Badge variant="light" color={standardStatusColor(item.status)}>
                              {item.status}
                            </Badge>
                            <Stack gap={0}>
                              <Text fw={500}>
                                {federation?.abbreviation || federation?.name || 'Unassigned'} • {item.season_year} • {item.weight_class_kg}kg
                              </Text>
                              <Text size="xs" c="dimmed">
                                {item.sex} • {item.equipment} • {item.event} • {item.required_total_kg}kg total
                              </Text>
                            </Stack>
                          </Group>
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Stack gap="md">
                            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                              <Select
                                searchable
                                label="Federation"
                                data={federationOptions}
                                value={item.federation_id}
                                onChange={(value) => updateStandard(item.id, { federation_id: value || '' })}
                              />
                              <TextInput
                                type="number"
                                label="Season Year"
                                value={item.season_year}
                                onChange={(e) => updateStandard(item.id, {
                                  season_year: Number(e.currentTarget.value) || item.season_year,
                                })}
                              />
                              <Select
                                label="Sex"
                                data={SEX_OPTIONS}
                                value={item.sex}
                                onChange={(value) => value && updateStandard(item.id, { sex: value as QualificationStandard['sex'] })}
                              />
                              <Select
                                label="Status"
                                data={STATUS_OPTIONS}
                                value={item.status}
                                onChange={(value) => value && updateStandard(item.id, { status: value as QualificationStandard['status'] })}
                              />
                            </SimpleGrid>

                            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                              <Select
                                label="Equipment"
                                data={EQUIPMENT_OPTIONS}
                                value={item.equipment}
                                onChange={(value) => value && updateStandard(item.id, { equipment: value as QualificationStandard['equipment'] })}
                              />
                              <Select
                                label="Event"
                                data={EVENT_OPTIONS}
                                value={item.event}
                                onChange={(value) => value && updateStandard(item.id, { event: value as QualificationStandard['event'] })}
                              />
                              <TextInput
                                label="Age Class"
                                value={item.age_class || ''}
                                onChange={(event) => updateStandard(item.id, { age_class: event.currentTarget.value || undefined })}
                              />
                              <TextInput
                                label="Division"
                                value={item.division || ''}
                                onChange={(event) => updateStandard(item.id, { division: event.currentTarget.value || undefined })}
                              />
                            </SimpleGrid>

                            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                              <TextInput
                                type="number"
                                label="Weight Class (kg)"
                                value={item.weight_class_kg}
                                onChange={(e) => updateStandard(item.id, {
                                  weight_class_kg: Number(e.currentTarget.value) || item.weight_class_kg,
                                })}
                              />
                              <TextInput
                                type="number"
                                label="Required Total (kg)"
                                value={item.required_total_kg}
                                onChange={(e) => updateStandard(item.id, {
                                  required_total_kg: Number(e.currentTarget.value) || item.required_total_kg,
                                })}
                              />
                              <DatePickerInput
                                clearable
                                label="Qualifying Start"
                                value={item.qualifying_start_date || null}
                                onChange={(value) => updateStandard(item.id, { qualifying_start_date: value || undefined })}
                              />
                              <DatePickerInput
                                clearable
                                label="Qualifying End"
                                value={item.qualifying_end_date || null}
                                onChange={(value) => updateStandard(item.id, { qualifying_end_date: value || undefined })}
                              />
                            </SimpleGrid>

                            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                              <TextInput
                                label="Competition Name"
                                value={item.competition_name || ''}
                                onChange={(event) => updateStandard(item.id, { competition_name: event.currentTarget.value || undefined })}
                              />
                              <TextInput
                                label="Source Label"
                                value={item.source_label || ''}
                                onChange={(event) => updateStandard(item.id, { source_label: event.currentTarget.value || undefined })}
                              />
                              <TextInput
                                label="Source URL"
                                value={item.source_url || ''}
                                onChange={(event) => updateStandard(item.id, { source_url: event.currentTarget.value || undefined })}
                              />
                            </SimpleGrid>

                            <Group justify="space-between">
                              <Text size="xs" c="dimmed">
                                {referencedStandardIds.has(item.id) ? 'Referenced by the current program.' : 'Not referenced by the current program.'}
                              </Text>
                              <Button
                                variant="light"
                                color={item.status === 'active' ? 'gray' : 'blue'}
                                leftSection={<Archive size={14} />}
                                onClick={() => updateStandard(item.id, {
                                  status: item.status === 'active' ? 'archived' : 'active',
                                })}
                              >
                                {item.status === 'active' ? 'Archive' : 'Restore'}
                              </Button>
                            </Group>
                          </Stack>
                        </Accordion.Panel>
                      </Accordion.Item>
                    )
                  })}
              </Accordion>
            )}
          </Stack>
        </>
      )}
    </Stack>
  )
}
