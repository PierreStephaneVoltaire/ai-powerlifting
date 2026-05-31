import { Center, Stack, Title, Text, Button, Box } from '@mantine/core'
import { Shield } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'

export function LoginPage() {
  const { signIn } = useAuth()

  return (
    <Center style={{ minHeight: '100vh' }}>
      <Stack align="center" gap="lg">
        <Box
          style={{
            width: 72,
            height: 72,
            borderRadius: 16,
            background: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Shield size={36} color="white" />
        </Box>
        <Stack align="center" gap={4}>
          <Title order={1} style={{ fontSize: '2rem' }}>
            IF Directives
          </Title>
          <Text c="dimmed" size="sm" ta="center" maw={300}>
            Manage behavioral directives for the IF agent. Sign in with Discord to continue.
          </Text>
        </Stack>
        <Button
          size="lg"
          variant="gradient"
          gradient={{ from: 'violet.6', to: 'violet.4' }}
          onClick={signIn}
        >
          Sign in with Discord
        </Button>
      </Stack>
    </Center>
  )
}