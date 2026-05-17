import { Alert, Button, Group } from '@mantine/core'
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
      <Group justify="space-between" wrap="nowrap" align="center">
        <span>You&#39;re viewing in read-only mode. Sign in to edit your data.</span>
        <Button
          size="compact-sm"
          variant="light"
          color="yellow"
          leftSection={<LogIn size={14} />}
          onClick={signIn}
        >
          Sign In
        </Button>
      </Group>
    </Alert>
  )
}
