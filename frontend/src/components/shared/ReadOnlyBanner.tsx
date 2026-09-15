import { Alert, Text } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import { routePermission } from '@/auth/routes'
import { useLocation } from 'react-router-dom'
import { Eye } from 'lucide-react'

export default function ReadOnlyBanner() {
  const location = useLocation()
  const { mapped_pk, permissions, readOnly } = useAuth()
  const permission = routePermission(location.pathname)

  if (!mapped_pk || !permission || !permissions.includes(permission) || !readOnly) return null

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
