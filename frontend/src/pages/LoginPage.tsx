import { Button, Center, Stack, Text, Paper, Group, Divider } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'
import { useSearchParams } from 'react-router-dom'

const DISCORD_ERROR_MESSAGES: Record<string, string> = {
  no_code: 'Discord authorization code was not received.',
  invalid_state: 'Security verification failed. Please try again.',
  auth_failed: 'Discord authentication failed. Please try again.',
}

const AUTHENTIK_ERROR_MESSAGES: Record<string, string> = {
  authentik_disabled: 'Authentik sign-in is not enabled on this server.',
  authentik_failed: 'Authentik authentication failed. Please try again.',
  no_code: 'Authorization code was not received.',
  invalid_state: 'Security verification failed. Please try again.',
}

function formatError(error: string | null): string {
  if (!error) return ''
  return (
    DISCORD_ERROR_MESSAGES[error] ||
    AUTHENTIK_ERROR_MESSAGES[error] ||
    'An error occurred during sign in.'
  )
}

export default function LoginPage() {
  const { signInDiscord, signInAuthentik } = useAuth()
  const [searchParams] = useSearchParams()
  const error = searchParams.get('error')
  const errorMessage = formatError(error)

  return (
    <Center h="100dvh">
      <Paper shadow="sm" p="xl" radius="md" w={400}>
        <Stack align="center" gap="lg">
          <Text size="xl" fw={700}>NoLift Training</Text>

          {errorMessage && (
            <Text c="red" size="sm">
              {errorMessage}
            </Text>
          )}

          <Group style={{ width: '100%' }}>
            <Button
              size="lg"
              onClick={signInDiscord}
              style={{ flex: 1 }}
              data-testid="signin-discord"
            >
              Sign in with Discord
            </Button>
          </Group>

          <Divider label="or" labelPosition="center" style={{ width: '100%' }} />

          <Group style={{ width: '100%' }}>
            <Button
              size="lg"
              variant="default"
              onClick={signInAuthentik}
              style={{ flex: 1 }}
              data-testid="signin-authentik"
            >
              Sign in
            </Button>
          </Group>

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

