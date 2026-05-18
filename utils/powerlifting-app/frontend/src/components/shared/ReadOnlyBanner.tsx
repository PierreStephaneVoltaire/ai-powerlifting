import { Alert, Button, Group, Text } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import { LogIn, Eye } from 'lucide-react'

export default function ReadOnlyBanner() {
  const { readOnly, signIn } = useAuth()

  if (!readOnly) return null

  return (
    <Alert
      variant="light"
      color="yellow"
      icon={<Eye size={18} />}
      mb="md"
      styles={{
        root: {
          borderRadius: 'var(--mantine-radius-md)',
        },
      }}
    >
      <Group justify="space-between" gap="xs" wrap="wrap" align="center">
        <Text size="sm" fw={500} style={{ flex: '1 1 8rem', minWidth: 0 }}>
          Read-only mode.
        </Text>
        <Button
          size="compact-sm"
          variant="light"
          color="yellow"
          leftSection={<LogIn size={14} />}
          onClick={signIn}
          style={{ flexShrink: 0 }}
        >
          Sign in
        </Button>
      </Group>
    </Alert>
  )
}
