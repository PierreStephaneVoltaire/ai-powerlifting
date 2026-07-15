import { Alert, Text } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import { Eye } from 'lucide-react'

export default function ReadOnlyBanner() {
  const { readOnly } = useAuth()

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
      <Text size="sm" fw={500}>
        Read-only mode.
      </Text>
    </Alert>
  )
}
