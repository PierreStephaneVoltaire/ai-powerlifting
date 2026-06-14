import { Button, Center, Stack, Text, Paper, Group, Image } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import { useSearchParams } from 'react-router-dom'

export default function LoginPage() {
  const { signIn } = useAuth()
  const [searchParams] = useSearchParams()
  const error = searchParams.get('error')

  const errorMessages: Record<string, string> = {
    no_code: 'Discord authorization code was not received.',
    invalid_state: 'Security verification failed. Please try again.',
    auth_failed: 'Discord authentication failed. Please try again.',
  }

  return (
    <Center h="100dvh">
      <Paper shadow="sm" p="xl" radius="md" w={400}>
        <Stack align="center" gap="lg">
          <Text size="xl" fw={700}>NoLift Training</Text>

          {error && (
            <Text c="red" size="sm">
              {errorMessages[error] || 'An error occurred during sign in.'}
            </Text>
          )}

          <Button
            size="lg"
            onClick={signIn}
            style={{ width: '100%' }}
          >
            <Group gap="xs">
              <Text>Sign in with Discord</Text>
            </Group>
          </Button>

          <Text size="xs" c="dimmed">
            Sign in to access your personal training data.
            <br />
            Without signing in, you'll see shared demo data.
          </Text>
        </Stack>
      </Paper>
    </Center>
  )
}
