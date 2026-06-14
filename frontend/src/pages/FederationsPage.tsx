import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Save, Shield } from 'lucide-react'
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
  Textarea,
  Title,
  TextInput,
} from '@mantine/core'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import { fetchUserFederations, patchUserFederation } from '@/api/client'
import type { UserFederation } from '@powerlifting/types'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
]

function federationStatusColor(status: UserFederation['user_status']): string {
  return status === 'active' ? 'blue' : 'gray'
}

export default function FederationsPage() {
  const { readOnly } = useAuth()
  const { pushToast } = useUiStore()
  const [federations, setFederations] = useState<UserFederation[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [hasChanges, setHasChanges] = useState(false)
  const [pendingPatches, setPendingPatches] = useState<Map<string, { user_status?: 'active' | 'archived'; notes?: string }>>(new Map())

  useEffect(() => {
    fetchUserFederations()
      .then((feds) => { setFederations(feds); setIsLoading(false) })
      .catch(() => { setIsLoading(false) })
  }, [])

  function updatePending(masterId: string, patch: { user_status?: 'active' | 'archived'; notes?: string }) {
    setPendingPatches((prev) => {
      const next = new Map(prev)
      const existing = next.get(masterId) || {}
      next.set(masterId, { ...existing, ...patch })
      return next
    })
    setHasChanges(true)
  }

  function getEffectiveStatus(masterId: string): 'active' | 'archived' {
    const fed = federations.find((f) => f.master_id === masterId)
    const pending = pendingPatches.get(masterId)
    return pending?.user_status ?? fed?.user_status ?? 'active'
  }

  function getEffectiveNotes(masterId: string): string {
    const fed = federations.find((f) => f.master_id === masterId)
    const pending = pendingPatches.get(masterId)
    return pending?.notes ?? fed?.notes ?? ''
  }

  async function handleSave() {
    try {
      for (const [masterId, patch] of pendingPatches) {
        await patchUserFederation(masterId, patch)
      }
      // Refresh from server
      const feds = await fetchUserFederations()
      setFederations(feds)
      setPendingPatches(new Map())
      setHasChanges(false)
      pushToast({ message: 'Federation changes saved', type: 'success' })
    } catch {
      pushToast({ message: 'Failed to save federation changes', type: 'error' })
    }
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>Designer</Text>
            <Text c="dimmed">/</Text>
            <Title order={2}>Federations</Title>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>
            Federation details are read-only. You can update your status and notes.
          </Text>
        </Stack>
        {hasChanges && (
          <Button leftSection={<Save size={16} />} onClick={handleSave} disabled={readOnly}>
            Save
          </Button>
        )}
      </Group>

      {isLoading ? (
        <Paper withBorder p="xl">
          <Group justify="center">
            <Text c="dimmed">Loading federations...</Text>
          </Group>
        </Paper>
      ) : federations.length === 0 ? (
        <Paper withBorder p="lg">
          <Text size="sm" c="dimmed">No federations found.</Text>
        </Paper>
      ) : (
        <Accordion variant="separated">
          {federations.map((fed) => {
            const effectiveStatus = getEffectiveStatus(fed.master_id)
            const effectiveNotes = getEffectiveNotes(fed.master_id)

            return (
              <Accordion.Item key={fed.master_id} value={fed.master_id}>
                <Accordion.Control>
                  <Group gap="sm" wrap="nowrap">
                    <Badge variant="light" color={federationStatusColor(effectiveStatus)}>
                      {effectiveStatus}
                    </Badge>
                    <Stack gap={0}>
                      <Text fw={500}>{fed.abbreviation || fed.name}</Text>
                      <Text size="xs" c="dimmed">{fed.name}</Text>
                    </Stack>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="md">
                    {/* Master fields (read-only) */}
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                      <TextInput label="Name" value={fed.name} readOnly />
                      <TextInput label="Abbreviation" value={fed.abbreviation || ''} readOnly />
                      <TextInput label="Region" value={fed.region || ''} readOnly />
                      {fed.website_url && (
                        <TextInput
                          label="Website"
                          value={fed.website_url}
                          readOnly
                          rightSection={
                            <Text component="a" href={fed.website_url} target="_blank" size="xs" c="blue" style={{ textDecoration: 'none' }}>Open</Text>
                          }
                        />
                      )}
                    </SimpleGrid>

                    {/* User-owned fields (editable) */}
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                      <Select
                        label="Your Status"
                        data={STATUS_OPTIONS}
                        value={effectiveStatus}
                        onChange={(value) => value && updatePending(fed.master_id, { user_status: value as 'active' | 'archived' })}
                        disabled={readOnly}
                      />
                    </SimpleGrid>
                    <Textarea
                      label="Notes"
                      autosize
                      minRows={2}
                      value={effectiveNotes}
                      onChange={(event) => updatePending(fed.master_id, { notes: event.currentTarget.value })}
                      disabled={readOnly}
                    />
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            )
          })}
        </Accordion>
      )}
    </Stack>
  )
}
