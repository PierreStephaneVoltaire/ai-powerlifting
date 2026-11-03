import { Center, Stack, Text, Paper } from '@mantine/core'
import { useSearchParams } from 'react-router-dom'
import LoginOptions from '@/components/auth/LoginOptions'

const DISCORD_ERROR_MESSAGES: Record<string, string> = {
  no_code: 'Discord authorization code was not received.',
  invalid_state: 'Security verification failed. Please try again.',
  auth_failed: 'Discord authentication failed. Please try again.',
}

const AUTHENTIK_ERROR_MESSAGES: Record<string, string> = {
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
  const [searchParams] = useSearchParams()
  const error = searchParams.get('error')
  const errorMessage = formatError(error)

  return (
    <Center mih="calc(100dvh - 140px)">
      <Paper shadow="sm" p={{ base: 'md', sm: 'xl' }} radius="md" w="100%" maw={400}>
        <Stack align="center" gap="lg">
          <Text size="xl" fw={700}>NoLift Training</Text>

          {errorMessage && (
            <Text c="red" size="sm">
              {errorMessage}
            </Text>
          )}

          <LoginOptions />

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
