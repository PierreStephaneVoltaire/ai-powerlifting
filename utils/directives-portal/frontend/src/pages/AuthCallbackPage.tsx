import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Center, Loader, Text, Stack } from '@mantine/core'

export function AuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const error = searchParams.get('error')
    if (error) {
      navigate(`/login?error=${error}`)
    } else {
      // Auth cookie is set; redirect to main app
      navigate('/')
    }
  }, [navigate, searchParams])

  return (
    <Center style={{ minHeight: '100vh' }}>
      <Stack align="center" gap="md">
        <Loader size="lg" />
        <Text c="dimmed">Signing you in...</Text>
      </Stack>
    </Center>
  )
}