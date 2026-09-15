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
          style={{ flex: 1, minHeight: 44 }}
          aria-label="Sign in with Discord"
          data-testid="signin-discord"
        >
          Discord
        </Button>
        <Button
          size="md"
          variant="default"
          onClick={signInAuthentik}
          style={{ flex: 1, minHeight: 44 }}
          aria-label="Sign in with Authentik"
          data-testid="signin-authentik"
        >
          Authentik
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
        Sign in with Discord
      </Button>

      <Divider label="or" labelPosition="center" />

      <Button
        size="lg"
        variant="default"
        onClick={signInAuthentik}
        style={{ width: '100%', minHeight: 44 }}
        data-testid="signin-authentik"
      >
        Sign in with Authentik
      </Button>
    </Stack>
  )
}
