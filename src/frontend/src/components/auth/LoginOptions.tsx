import { Button, Divider, Group, Stack } from '@mantine/core'
import { useAuth } from '@/auth/AuthProvider'

interface LoginOptionsProps {
  compact?: boolean
}

export default function LoginOptions({ compact = false }: LoginOptionsProps) {
  const { signInDiscord, signInAuthentik } = useAuth()

  if (compact) {
    return (
      <Group gap="sm" wrap="nowrap" w="100%">
        <Button
          size="md"
          onClick={signInDiscord}
          style={{ flex: 1, minHeight: 44, height: 'auto' }}
          styles={{ label: { whiteSpace: 'normal', textAlign: 'center' } }}
          aria-label="Log in with Discord"
          data-testid="signin-discord"
        >
          Log in with Discord
        </Button>
        <Button
          size="md"
          variant="default"
          onClick={signInAuthentik}
          style={{ flex: 1, minHeight: 44, height: 'auto' }}
          styles={{ label: { whiteSpace: 'normal', textAlign: 'center' } }}
          aria-label="Log in"
          data-testid="signin-authentik"
        >
          Log in
        </Button>
      </Group>
    )
  }

  return (
    <Stack gap="sm" w="100%">
      <Button
        size="lg"
        onClick={signInDiscord}
        style={{ width: '100%', minHeight: 44 }}
        data-testid="signin-discord"
      >
        Log in with Discord
      </Button>

      <Divider label="or" labelPosition="center" />

      <Button
        size="lg"
        variant="default"
        onClick={signInAuthentik}
        style={{ width: '100%', minHeight: 44 }}
        data-testid="signin-authentik"
      >
        Log in
      </Button>
    </Stack>
  )
}
