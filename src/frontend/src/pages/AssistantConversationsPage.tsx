import { useEffect, useState } from 'react'
import { Stack, Group, Paper, Text, Badge, Loader, Alert, UnstyledButton } from '@mantine/core'
import { fetchConversations, type AssistantConversation } from '@/api/assistant'
import { useAuth } from '@/auth/AuthProvider'
import AssistantDrawer from '@/components/assistant/AssistantDrawer'

function labelOf(item: AssistantConversation): string {
  if (item.label) return item.label
  return item.kind === 'discord' ? `Discord ${item.scope}` : 'General chat'
}

export default function AssistantConversationsPage() {
  const { readOnly } = useAuth()
  const [items, setItems] = useState<AssistantConversation[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<AssistantConversation | null>(null)

  useEffect(() => {
    fetchConversations().then(setItems).catch(() => setError('Could not load conversations.'))
  }, [])

  return (
    <Stack gap="md" className="if-mock-page">
      <div className="if-mock-header">
        <div>
          <h1 className="if-mock-title">Assistant</h1>
          <div className="if-mock-subtitle">General conversations and shared Discord conversations.</div>
        </div>
      </div>
      {error && <Alert color="red">{error}</Alert>}
      {!items && !error && <Loader size="sm" />}
      {items && items.length === 0 && <Text size="sm" c="dimmed">No conversations yet.</Text>}
      <Stack gap={4}>
        {items?.map((item) => (
          <Paper key={item.id} withBorder p="xs" radius="sm">
            <UnstyledButton onClick={() => setOpen(item)} style={{ width: '100%' }}>
              <Group gap="xs" wrap="nowrap">
                <Text size="sm" truncate style={{ flex: 1 }}>{labelOf(item)}</Text>
                <Badge variant="light" color={item.kind === 'discord' ? 'indigo' : 'grape'}>{item.kind === 'discord' ? 'Discord' : 'General'}</Badge>
                <Text size="xs" c="dimmed">{new Date(item.updated_at).toLocaleString()}</Text>
              </Group>
            </UnstyledButton>
          </Paper>
        ))}
      </Stack>
      <AssistantDrawer
        opened={open !== null}
        onClose={() => setOpen(null)}
        scope="general"
        context={{}}
        readOnly={readOnly}
        conversationId={open?.kind === 'discord' ? open.id : undefined}
      />
    </Stack>
  )
}
