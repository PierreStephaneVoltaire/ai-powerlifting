import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Center, Loader, Stack, Text } from '@mantine/core'

export default function AuthCallbackPage() {
  const navigate = useNavigate()

  useEffect(() => {
    // The backend already set the httpOnly cookie via the Discord callback redirect.
    // Just verify we're authed and go home.
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(() => navigate('/', { replace: true }))
      .catch(() => navigate('/login?error=auth_failed', { replace: true }))
  }, [navigate])

  return (
    <Center h="100dvh">
      <Stack align="center" gap="md">
        <Loader size="lg" />
        <Text>Signing you in...</Text>
      </Stack>
    </Center>
  )
}
