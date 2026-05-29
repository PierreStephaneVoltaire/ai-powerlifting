import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DndContext, DragEndEvent, DragStartEvent,
  PointerSensor, useSensor, useSensors, closestCenter,
  DragOverlay,
} from '@dnd-kit/core'
import { Center, Group, Stack, Loader, Text, Button, AppShell, Avatar, Menu, Box } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { Shield, Plus, LogOut, RefreshCw } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { useDirectivesStore } from '../store/directivesStore'
import { Directive } from '../api/client'
import { TierColumn } from '../components/TierColumn'
import { DirectiveDetailModal } from '../components/DirectiveDetailModal'
import { NewDirectiveModal } from '../components/NewDirectiveModal'

export function DirectivesPage() {
  const navigate = useNavigate()
  const { user, loading: authLoading, signOut } = useAuth()
  const {
    directives, loading, error, history, historyLoading,
    fetchAll, create, revise, reorder, remove,
    fetchHistory, clearHistory,
  } = useDirectivesStore()

  const [selectedDirective, setSelectedDirective] = useState<Directive | null>(null)
  const [showNewModal, setShowNewModal] = useState(false)
  const [activeDragDirective, setActiveDragDirective] = useState<Directive | null>(null)

  // Auth gate
  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login')
    }
  }, [authLoading, user, navigate])

  // Load directives
  useEffect(() => {
    if (user) fetchAll()
  }, [user])

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const id = String(event.active.id)
    const d = directives.find(d => `${d.alpha}-${d.beta}` === id)
    if (d) setActiveDragDirective(d)
  }, [directives])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    setActiveDragDirective(null)
    const { active, over } = event
    if (!over) return

    const activeId = String(active.id)
    const overId = String(over.id)

    if (activeId === overId) return

    const activeD = directives.find(d => `${d.alpha}-${d.beta}` === activeId)
    if (!activeD) return

    let newAlpha: number
    let newBeta: number

    if (overId.startsWith('tier-')) {
      // Dropped on a tier column header
      newAlpha = parseInt(overId.replace('tier-', ''), 10)
      const existingInTier = directives.filter(d => d.alpha === newAlpha)
      newBeta = existingInTier.length > 0 ? Math.max(...existingInTier.map(d => d.beta)) + 1 : 1
    } else {
      // Dropped on another directive card — insert before it
      const overD = directives.find(d => `${d.alpha}-${d.beta}` === overId)
      if (!overD) return
      newAlpha = overD.alpha
      newBeta = overD.beta
    }

    if (activeD.alpha === newAlpha && activeD.beta === newBeta) return

    try {
      const result = await reorder(activeD.alpha, activeD.beta, newAlpha, newBeta)
      notifications.show({
        title: 'Directive reordered',
        message: `Moved to ${result.alpha}-${result.beta}`,
        color: 'violet',
      })
    } catch (err) {
      notifications.show({
        title: 'Reorder failed',
        message: err instanceof Error ? err.message : 'Unknown error',
        color: 'red',
      })
    }
  }, [directives, reorder])

  const handleEdit = (d: Directive) => setSelectedDirective(d)

  const handleDelete = async (d: Directive) => {
    if (!confirm(`Delete directive ${d.alpha}-${d.beta} (${d.label})?`)) return
    try {
      await remove(d.alpha, d.beta)
      notifications.show({ title: 'Deleted', message: `Directive ${d.alpha}-${d.beta} deactivated`, color: 'red' })
    } catch (err) {
      notifications.show({ title: 'Delete failed', message: err instanceof Error ? err.message : 'Unknown error', color: 'red' })
    }
  }

  const handleCreate = async (input: Parameters<typeof create>[0]) => {
    try {
      const d = await create(input)
      notifications.show({ title: 'Created', message: `Directive ${d.alpha}-${d.beta} added`, color: 'violet' })
    } catch (err) {
      notifications.show({ title: 'Create failed', message: err instanceof Error ? err.message : 'Unknown error', color: 'red' })
      throw err
    }
  }

  const handleSave = async (alpha: number, beta: number, input: Parameters<typeof revise>[2]) => {
    try {
      await revise(alpha, beta, input)
      notifications.show({ title: 'Saved', message: `Directive ${alpha}-${beta} updated`, color: 'violet' })
    } catch (err) {
      notifications.show({ title: 'Save failed', message: err instanceof Error ? err.message : 'Unknown error', color: 'red' })
      throw err
    }
  }

  // Group directives by alpha tier
  const byTier = Array.from({ length: 6 }, (_, i) => i).map(alpha => ({
    alpha,
    directives: directives.filter(d => d.alpha === alpha).sort((a, b) => a.beta - b.beta),
  }))

  if (authLoading) {
    return (
      <Center style={{ minHeight: '100vh' }}>
        <Loader size="lg" />
      </Center>
    )
  }

  if (!user) return null

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <AppShell header={{ height: 60 }} padding="md">
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <Group gap={10}>
              <Box
                style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <Shield size={18} color="white" />
              </Box>
              <Text fw={700} size="lg" style={{ fontFamily: "'Barlow Condensed', sans-serif" }}>
                IF Directives
              </Text>
            </Group>

            <Group gap="sm">
              <Button
                variant="gradient"
                gradient={{ from: 'violet.6', to: 'violet.4' }}
                size="sm"
                leftSection={<Plus size={14} />}
                onClick={() => setShowNewModal(true)}
              >
                New Directive
              </Button>
              <Button
                variant="subtle"
                color="gray"
                size="sm"
                leftSection={<RefreshCw size={14} />}
                onClick={() => fetchAll()}
                disabled={loading}
              >
                Refresh
              </Button>
              <Menu shadow="md" width={200}>
                <Menu.Target>
                  <Button variant="subtle" color="gray" size="sm" p={4}>
                    <Avatar
                      src={user.avatar}
                      size={28}
                      radius="xl"
                      alt={user.username}
                    >
                      {user.username[0].toUpperCase()}
                    </Avatar>
                  </Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>{user.username}</Menu.Label>
                  <Menu.Item
                    leftSection={<LogOut size={14} />}
                    color="red"
                    onClick={signOut}
                  >
                    Sign out
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Main>
          {error && (
            <Box mb="md" p="sm" style={{ background: 'var(--mantine-color-red-0)', borderRadius: 8, border: '1px solid var(--mantine-color-red-5)' }}>
              <Text size="sm" c="red">{error}</Text>
            </Box>
          )}

          {loading && directives.length === 0 ? (
            <Center py="xl"><Loader /></Center>
          ) : (
            <Stack gap="md">
              <Group gap="md" wrap="nowrap" align="stretch" style={{ overflowX: 'auto', paddingBottom: 8 }}>
                {byTier.map(({ alpha, directives: tierDirs }) => (
                  <TierColumn
                    key={alpha}
                    alpha={alpha}
                    directives={tierDirs}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                  />
                ))}
              </Group>
            </Stack>
          )}
        </AppShell.Main>
      </AppShell>

      <DragOverlay>
        {activeDragDirective && (
          <Box
            style={{
              background: 'var(--bg-surface)',
              border: '2px solid var(--mantine-color-violet-5)',
              borderRadius: 8,
              padding: 12,
              boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
              opacity: 0.95,
              width: 236,
            }}
          >
            <Text size="xs" fw={700} c="violet.6" ff="'IBM Plex Mono', monospace">
              {activeDragDirective.alpha}-{activeDragDirective.beta}
            </Text>
            <Text size="sm" fw={600}>{activeDragDirective.label}</Text>
          </Box>
        )}
      </DragOverlay>

      <DirectiveDetailModal
        directive={selectedDirective}
        history={history}
        historyLoading={historyLoading}
        onClose={() => setSelectedDirective(null)}
        onSave={handleSave}
        onDelete={async (alpha, beta) => {
          await remove(alpha, beta)
          setSelectedDirective(null)
        }}
        onFetchHistory={fetchHistory}
        onClearHistory={clearHistory}
      />

      <NewDirectiveModal
        opened={showNewModal}
        onClose={() => setShowNewModal(false)}
        onCreate={handleCreate}
      />
    </DndContext>
  )
}
