import { useEffect, useState, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Center, Group, Stack, Loader, Text, Button, AppShell, Avatar, Menu, Box,
  ActionIcon, TextInput, Badge, SegmentedControl, useMantineTheme,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { Shield, Plus, LogOut, RefreshCw, Search, ArrowUpDown, Save, X } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { useDirectivesStore } from '../store/directivesStore'
import { Directive, BulkReorderItem } from '../api/client'
import { DirectiveCard } from '../components/DirectiveCard'
import { SortableDirectiveCard } from '../components/SortableDirectiveCard'
import { DirectiveDetailModal } from '../components/DirectiveDetailModal'
import { NewDirectiveModal } from '../components/NewDirectiveModal'

const TIER_META: Record<number, { label: string; description: string; color: string }> = {
  0: { label: 'Tier 0', description: 'Fundamental — Never break', color: '#dc2626' },
  1: { label: 'Tier 1', description: 'Critical — Only bypass with explicit request', color: '#ea580c' },
  2: { label: 'Tier 2', description: 'Standard — Recommended', color: '#ca8a04' },
  3: { label: 'Tier 3', description: 'Preference — Optional but encouraged', color: '#2563eb' },
  4: { label: 'Tier 4', description: 'Advisory — Consider', color: '#0d9488' },
  5: { label: 'Tier 5', description: 'Notes — Background context', color: '#6b7280' },
}

const TYPE_OPTIONS = [
  'core', 'code', 'health', 'finance', 'memory', 'security', 'style', 'tool', 'metacognition', 'architecture',
]

interface ReorderDirective extends Directive {
  _origAlpha: number
  _origBeta: number
}

function toReorderDirective(d: Directive): ReorderDirective {
  return { ...d, _origAlpha: d.alpha, _origBeta: d.beta }
}

/** Compute next beta for a target alpha from the current reordered list. */
function nextBetaForAlpha(directives: ReorderDirective[], targetAlpha: number): number {
  let max = 0
  for (const d of directives) {
    if (d.alpha === targetAlpha && d.beta > max) max = d.beta
  }
  return max + 1
}

export function DirectivesPage() {
  const navigate = useNavigate()
  const { user, loading: authLoading, signOut, isOperator } = useAuth()
  const {
    directives, loading, error, history, historyLoading,
    fetchAll, create, revise, bulkReorder, remove,
    fetchHistory, clearHistory,
  } = useDirectivesStore()

  const [selectedDirective, setSelectedDirective] = useState<Directive | null>(null)
  const [showNewModal, setShowNewModal] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [tierFilter, setTierFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const [reorderMode, setReorderMode] = useState(false)
  const [reorderedDirectives, setReorderedDirectives] = useState<ReorderDirective[]>([])
  const [savingReorder, setSavingReorder] = useState(false)
  const [draggedDirective, setDraggedDirective] = useState<ReorderDirective | null>(null)

  useEffect(() => {
    if (!authLoading && !user) navigate('/login')
  }, [authLoading, user, navigate])

  useEffect(() => {
    if (user) fetchAll()
  }, [user])

  const handleEdit = (d: Directive) => {
    if (d.read_only) return
    setSelectedDirective(d)
  }

  const handleDelete = async (d: Directive) => {
    if (d.read_only) return
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

  // ── Reorder Mode ──────────────────────────────────────────────────────────

  const enterReorderMode = useCallback(() => {
    setReorderedDirectives(directives.map(toReorderDirective))
    setReorderMode(true)
  }, [directives])

  const exitReorderMode = useCallback(() => {
    setReorderMode(false)
    setReorderedDirectives([])
    setDraggedDirective(null)
  }, [])

  const pendingChanges = useMemo((): BulkReorderItem[] => {
    if (!reorderMode) return []
    const changes: BulkReorderItem[] = []
    for (const rd of reorderedDirectives) {
      if (rd._origAlpha !== rd.alpha || rd._origBeta !== rd.beta) {
        changes.push({
          old_alpha: rd._origAlpha,
          old_beta: rd._origBeta,
          new_alpha: rd.alpha,
          new_beta: rd.beta,
        })
      }
    }
    return changes
  }, [reorderMode, reorderedDirectives])

  const hasPendingChanges = pendingChanges.length > 0

  const handleSaveReorder = async () => {
    if (!hasPendingChanges) return
    setSavingReorder(true)
    try {
      await bulkReorder(pendingChanges)
      notifications.show({ title: 'Ranking saved', message: `${pendingChanges.length} directive(s) reordered`, color: 'green' })
      exitReorderMode()
    } catch (err) {
      notifications.show({ title: 'Reorder failed', message: err instanceof Error ? err.message : 'Unknown error', color: 'red' })
    } finally {
      setSavingReorder(false)
    }
  }

  // ── Tier Move (upgrade / downgrade) ───────────────────────────────────────

  const handleMoveTier = useCallback((
    origAlpha: number,
    origBeta: number,
    direction: 'up' | 'down'
  ) => {
    setReorderedDirectives(prev => {
      const idx = prev.findIndex(d => d._origAlpha === origAlpha && d._origBeta === origBeta)
      if (idx === -1) return prev
      const d = prev[idx]
      const targetAlpha = direction === 'up' ? d.alpha - 1 : d.alpha + 1
      if (targetAlpha < 0 || targetAlpha > 5) return prev
      const newBeta = nextBetaForAlpha(prev, targetAlpha)
      const updated = [...prev]
      updated[idx] = { ...d, alpha: targetAlpha, beta: newBeta }
      return updated
    })
  }, [])

  // ── DnD (cross-tier) ──────────────────────────────────────────────────────

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragStart = (event: { active: { id: string | number } }) => {
    const id = String(event.active.id)
    const directive = reorderedDirectives.find(d => `${d._origAlpha}-${d._origBeta}` === id)
    setDraggedDirective(directive ?? null)
  }

  const handleDragEnd = (event: { active: { id: string | number }; over: { id: string | number } | null }) => {
    setDraggedDirective(null)
    const { active, over } = event
    if (!over || active.id === over.id) return
    const activeId = String(active.id)
    const overId = String(over.id)
    const activeDirective = reorderedDirectives.find(d => `${d._origAlpha}-${d._origBeta}` === activeId)
    const overDirective = reorderedDirectives.find(d => `${d._origAlpha}-${d._origBeta}` === overId)
    if (!activeDirective || !overDirective) return
    // Block dragging global directives for non-operators
    if (activeDirective.global_directive && !isOperator) return
    if (overDirective.global_directive && !isOperator) return

    const newReordered = reorderedDirectives.map(d => {
      const dId = `${d._origAlpha}-${d._origBeta}`
      if (dId === activeId) {
        // Active directive takes over's position (swap across tiers)
        return { ...d, alpha: overDirective.alpha, beta: overDirective.beta }
      }
      if (dId === overId) {
        // Over directive takes active's position
        return { ...d, alpha: activeDirective.alpha, beta: activeDirective.beta }
      }
      return d
    })
    setReorderedDirectives(newReordered)
  }

  const handleDragCancel = () => { setDraggedDirective(null) }

  // ── Filtering & Grouping ──────────────────────────────────────────────────

  const sourceDirectives = reorderMode ? reorderedDirectives : directives

  const filteredDirectives = useMemo(() => {
    let result = [...sourceDirectives]
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(d => d.label.toLowerCase().includes(q) || d.content.toLowerCase().includes(q))
    }
    if (tierFilter !== 'all') {
      result = result.filter(d => d.alpha === parseInt(tierFilter, 10))
    }
    if (typeFilter !== 'all') {
      result = result.filter(d => d.types?.includes(typeFilter))
    }
    result.sort((a, b) => a.alpha - b.alpha || a.beta - b.beta)
    return result
  }, [sourceDirectives, searchQuery, tierFilter, typeFilter])

  const groupedDirectives = useMemo(() => {
    const groups: { alpha: number; directives: typeof filteredDirectives }[] = []
    let currentAlpha = -1
    for (const d of filteredDirectives) {
      if (d.alpha !== currentAlpha) {
        groups.push({ alpha: d.alpha, directives: [] })
        currentAlpha = d.alpha
      }
      groups[groups.length - 1].directives.push(d)
    }
    return groups
  }, [filteredDirectives])

  const theme = useMantineTheme()
  const smBreakpoint = typeof theme.breakpoints.sm === 'string' ? parseFloat(theme.breakpoints.sm) : theme.breakpoints.sm
  const isMobile = useMediaQuery(`(max-width: ${(smBreakpoint * 16) - 1}px)`)

  if (authLoading) return <Center style={{ minHeight: '100vh' }}><Loader size="lg" /></Center>
  if (!user) return null

  return (
    <AppShell header={{ height: isMobile ? 56 : 60 }} padding={0}>
      <AppShell.Header>
        <Group h="100%" px={isMobile ? 'sm' : 'md'} justify="space-between" wrap="nowrap">
          <Group gap={8} style={{ flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
            <Box style={{ width: isMobile ? 28 : 32, height: isMobile ? 28 : 32, borderRadius: 8, background: 'var(--mantine-color-violet-6)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <Shield size={isMobile ? 15 : 18} color="white" />
            </Box>
            {!isMobile && <Text fw={600} size="lg" ff="var(--font-sans)" c="var(--text-primary)" truncate>IF Directives</Text>}
          </Group>
          <Group gap={isMobile ? 4 : 'sm'} wrap="nowrap">
            {reorderMode ? (
              <>
                {isMobile ? (
                  <>
                    <ActionIcon variant="subtle" color="red" size="lg" onClick={exitReorderMode} aria-label="Cancel reorder"><X size={18} /></ActionIcon>
                    <ActionIcon variant="gradient" gradient={{ from: 'green.6', to: 'green.4' }} size="lg" onClick={handleSaveReorder} disabled={!hasPendingChanges || savingReorder} aria-label="Save ranking"><Save size={18} /></ActionIcon>
                  </>
                ) : (
                  <>
                    <Button variant="subtle" color="red" size="sm" leftSection={<X size={14} />} onClick={exitReorderMode}>Cancel</Button>
                    <Button variant="gradient" gradient={{ from: 'green.6', to: 'green.4' }} size="sm" leftSection={<Save size={14} />} onClick={handleSaveReorder} disabled={!hasPendingChanges} loading={savingReorder}>Save Ranking{hasPendingChanges ? ` (${pendingChanges.length})` : ''}</Button>
                  </>
                )}
              </>
            ) : (
              <>
                {isMobile ? (
                  <>
                    <ActionIcon variant="subtle" color="gray" size="lg" onClick={enterReorderMode} aria-label="Reorder"><ArrowUpDown size={18} /></ActionIcon>
                    <ActionIcon variant="gradient" gradient={{ from: 'violet.6', to: 'violet.4' }} size="lg" onClick={() => setShowNewModal(true)} aria-label="New directive"><Plus size={18} /></ActionIcon>
                    <ActionIcon variant="subtle" color="gray" size="lg" onClick={() => fetchAll()} disabled={loading} aria-label="Refresh"><RefreshCw size={18} /></ActionIcon>
                  </>
                ) : (
                  <>
                    <Button variant="subtle" color="gray" size="sm" leftSection={<ArrowUpDown size={14} />} onClick={enterReorderMode}>Reorder</Button>
                    <Button variant="gradient" gradient={{ from: 'violet.6', to: 'violet.4' }} size="sm" leftSection={<Plus size={14} />} onClick={() => setShowNewModal(true)}>New Directive</Button>
                    <Button variant="subtle" color="gray" size="sm" leftSection={<RefreshCw size={14} />} onClick={() => fetchAll()} disabled={loading}>Refresh</Button>
                  </>
                )}
              </>
            )}
            <Menu shadow="md" width={200}>
              <Menu.Target>
                <Button variant="subtle" color="gray" size="sm" p={4}>
                  <Avatar src={user.avatar} size={28} radius="xl" alt={user.username}>{user.username[0].toUpperCase()}</Avatar>
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>{user.username}</Menu.Label>
                <Menu.Item leftSection={<LogOut size={14} />} color="red" onClick={signOut}>Sign out</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Box style={{ position: 'sticky', top: isMobile ? 56 : 60, zIndex: 100, background: 'var(--bg-base)', borderBottom: '0.5px solid var(--border-subtle)', padding: isMobile ? '8px 12px' : '12px 20px' }}>
          <Stack gap={isMobile ? 6 : 8}>
            {!reorderMode && (
              <TextInput placeholder="Search directives by label or content..." leftSection={<Search size={14} />} value={searchQuery} onChange={e => setSearchQuery(e.currentTarget.value)} size="sm" style={{ width: '100%' }} />
            )}
            {reorderMode && (
              <Box p="xs" style={{ background: 'var(--status-warning-bg)', borderRadius: 8, border: '0.5px solid var(--status-warning-border)' }}>
                <Text size="xs" c="var(--status-warning-text)" fw={600}>
                  Reorder mode: Drag to swap within or across tiers. Use arrows to upgrade/downgrade tier. Global directives only movable by operator. Click &quot;Save Ranking&quot; to confirm.
                </Text>
              </Box>
            )}
            {!reorderMode && (
              <>
                <Group gap={isMobile ? 4 : 6} wrap="wrap">
                  <Text size="xs" c="dimmed" fw={600} style={{ marginRight: 4 }}>Tier:</Text>
                  <SegmentedControl size="xs" value={tierFilter} onChange={setTierFilter} data={[{ value: 'all', label: 'All' }, ...Array.from({ length: 6 }, (_, i) => ({ value: String(i), label: `T${i}` }))]} />
                </Group>
                <Group gap={isMobile ? 4 : 6} wrap="wrap">
                  <Text size="xs" c="dimmed" fw={600} style={{ marginRight: 4 }}>Type:</Text>
                  <SegmentedControl size="xs" value={typeFilter} onChange={setTypeFilter} data={[{ value: 'all', label: 'All' }, ...TYPE_OPTIONS.map(t => ({ value: t, label: t }))]} />
                </Group>
              </>
            )}
            <Group gap={8}>
              <Text size="xs" c="dimmed">{filteredDirectives.length} directive{filteredDirectives.length !== 1 ? 's' : ''}</Text>
              {searchQuery && !reorderMode && <Badge size="xs" variant="light" color="violet">searching &quot;{searchQuery}&quot;</Badge>}
              {hasPendingChanges && <Badge size="xs" variant="light" color="orange">{pendingChanges.length} pending change{pendingChanges.length !== 1 ? 's' : ''}</Badge>}
            </Group>
          </Stack>
        </Box>

        {error && (
          <Box mx={isMobile ? 12 : 20} mt="sm" p="sm" style={{ background: 'var(--status-danger-bg)', borderRadius: 8, border: '0.5px solid var(--status-danger-border)' }}>
            <Text size="sm" c="red">{error}</Text>
          </Box>
        )}

        {loading && directives.length === 0 ? (
          <Center py="xl"><Loader /></Center>
        ) : filteredDirectives.length === 0 ? (
          <Center py="xl">
            <Stack align="center" gap="xs">
              <Text size="sm" c="dimmed">No directives found</Text>
              {searchQuery && <Text size="xs" c="dimmed">Try adjusting your search or filters</Text>}
            </Stack>
          </Center>
        ) : reorderMode ? (
          // Single DndContext wrapping all tiers for cross-tier drag-and-drop
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <Stack gap={0} style={{ padding: isMobile ? '0 12px 24px' : '0 20px 24px' }}>
              {groupedDirectives.map(({ alpha, directives: tierDirs }) => {
                const meta = TIER_META[alpha] ?? { label: `Tier ${alpha}`, description: '', color: '#6b7280' }
                const tierSortableIds = tierDirs.map(d => {
                  const rd = d as ReorderDirective
                  return `${rd._origAlpha ?? rd.alpha}-${rd._origBeta ?? rd.beta}`
                })
                return (
                  <Box key={alpha}>
                    <Group gap={8} py="sm" style={{ position: 'sticky', top: isMobile ? 186 : 178, zIndex: 50, background: 'var(--bg-base)', borderBottom: `2px solid ${meta.color}` }}>
                      <Box style={{ width: 10, height: 10, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
                      <Text fw={700} size="sm" ff="var(--font-sans)">{meta.label}</Text>
                      <Text size="xs" c="dimmed">{meta.description}</Text>
                      <Badge size="xs" variant="light" color="gray" ml="auto">{tierDirs.length}</Badge>
                    </Group>
                    <SortableContext items={tierSortableIds} strategy={verticalListSortingStrategy}>
                      <Stack gap={isMobile ? 6 : 8} pb="md">
                        {tierDirs.map(d => {
                          const rd = d as ReorderDirective
                          const stableId = `${rd._origAlpha ?? rd.alpha}-${rd._origBeta ?? rd.beta}`
                          const canMove = !d.global_directive || isOperator
                          return (
                            <SortableDirectiveCard
                              key={stableId}
                              directive={d}
                              onEdit={handleEdit}
                              onDelete={handleDelete}
                              isOperator={isOperator}
                              reorderMode={reorderMode}
                              originalAlpha={rd._origAlpha ?? rd.alpha}
                              originalBeta={rd._origBeta ?? rd.beta}
                              canMove={canMove}
                              onMoveTier={handleMoveTier}
                              currentAlpha={d.alpha}
                            />
                          )
                        })}
                      </Stack>
                    </SortableContext>
                  </Box>
                )
              })}
            </Stack>
            <DragOverlay>
              {draggedDirective && (
                <DirectiveCard
                  directive={draggedDirective}
                  onEdit={() => {}}
                  onDelete={() => {}}
                  isOperator={isOperator}
                  reorderMode
                  originalAlpha={draggedDirective._origAlpha}
                  originalBeta={draggedDirective._origBeta}
                  canMove={!draggedDirective.global_directive || isOperator}
                  onMoveTier={handleMoveTier}
                  currentAlpha={draggedDirective.alpha}
                />
              )}
            </DragOverlay>
          </DndContext>
        ) : (
          // Normal (non-reorder) mode
          <Stack gap={0} style={{ padding: isMobile ? '0 12px 24px' : '0 20px 24px' }}>
            {groupedDirectives.map(({ alpha, directives: tierDirs }) => {
              const meta = TIER_META[alpha] ?? { label: `Tier ${alpha}`, description: '', color: '#6b7280' }
              return (
                <Box key={alpha}>
                  <Group gap={8} py="sm" style={{ position: 'sticky', top: isMobile ? 186 : 178, zIndex: 50, background: 'var(--bg-base)', borderBottom: `2px solid ${meta.color}` }}>
                    <Box style={{ width: 10, height: 10, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
                    <Text fw={700} size="sm" ff="var(--font-sans)">{meta.label}</Text>
                    <Text size="xs" c="dimmed">{meta.description}</Text>
                    <Badge size="xs" variant="light" color="gray" ml="auto">{tierDirs.length}</Badge>
                  </Group>
                  <Stack gap={isMobile ? 6 : 8} pb="md">
                    {tierDirs.map(d => (
                      <DirectiveCard key={`${d.alpha}-${d.beta}`} directive={d} onEdit={handleEdit} onDelete={handleDelete} isOperator={isOperator} />
                    ))}
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        )}
      </AppShell.Main>

      <DirectiveDetailModal
        directive={selectedDirective}
        history={history}
        historyLoading={historyLoading}
        onClose={() => setSelectedDirective(null)}
        onSave={handleSave}
        onDelete={async (alpha, beta) => { await remove(alpha, beta); setSelectedDirective(null) }}
        onFetchHistory={fetchHistory}
        onClearHistory={clearHistory}
        isOperator={isOperator}
      />

      <NewDirectiveModal opened={showNewModal} onClose={() => setShowNewModal(false)} onCreate={handleCreate} isOperator={isOperator} />
    </AppShell>
  )
}
