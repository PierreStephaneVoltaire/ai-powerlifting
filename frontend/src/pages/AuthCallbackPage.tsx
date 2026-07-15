import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Center, Loader, Stack, Text } from '@mantine/core'
import { getOnboardingStatus } from '@/api/onboarding'

export default function AuthCallbackPage() {
  const navigate = useNavigate()

  useEffect(() => {
    // The backend already set the httpOnly cookie via the Discord callback redirect.
    // Verify we're authed, then route to the dashboard OR to onboarding if the
    // user hasn't finished role / profile / athlete basics yet.
    let cancelled = false
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(async () => {
        if (cancelled) return
        try {
          const status = await getOnboardingStatus()
          if (cancelled) return
          if (!status.is_onboarded && status.next_step && status.next_step !== 'done') {
            navigate('/onboarding', { replace: true })
            return
          }
        } catch {
          // Fall through to the dashboard if the onboarding check fails.
        }
        navigate('/', { replace: true })
      })
      .catch(() => {
        if (!cancelled) navigate('/login?error=auth_failed', { replace: true })
      })
    return () => {
      cancelled = true
    }
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
