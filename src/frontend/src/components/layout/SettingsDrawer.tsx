import { Link } from 'react-router-dom'
import {
  Avatar,
  Button,
  Drawer,
  Group,
  Stack,
  Text,
} from '@mantine/core'
import { LogOut } from 'lucide-react'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import LoginOptions from '@/components/auth/LoginOptions'

export default function SettingsDrawer() {
  const { drawerOpen, drawerType, closeDrawer } = useUiStore()
  const { user, loading, signOut } = useAuth('settings')

  return (
    <Drawer
      opened={drawerOpen && drawerType === 'settings'}
      onClose={closeDrawer}
      title="Settings"
      position="right"
      size="sm"
      shadow="md"
      styles={{
        content: {
          background: 'var(--bg-surface)',
          color: 'var(--text-primary)',
        },
        header: {
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
        },
      }}
    >
      {loading ? (
        <Text size="xs" c="dimmed">Loading account...</Text>
      ) : user ? (
        <Stack gap="xs">
          <Group gap="sm">
            <Avatar src={user.avatar} alt={user.username} size={32} radius="xl">
              {user.username[0]?.toUpperCase()}
            </Avatar>
            <Stack gap={0}>
              <Text size="sm" fw={600}>{user.username}</Text>
              <Text size="xs" c="dimmed">Signed in</Text>
            </Stack>
          </Group>
          <Button component={Link} to="/onboarding?edit=1" variant="light" onClick={closeDrawer}>Edit roles, basics and federations</Button>
          <Button
            variant="light"
            color="red"
            size="sm"
            leftSection={<LogOut size={16} />}
            onClick={signOut}
            fullWidth
          >
            Sign out
          </Button>
        </Stack>
      ) : (
        <LoginOptions compact />
      )}
    </Drawer>
  )
}
