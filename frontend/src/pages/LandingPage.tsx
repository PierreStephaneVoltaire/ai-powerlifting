import { Activity, Search, ShieldCheck } from 'lucide-react'
import { Button, Center, Container, Group, Paper, Stack, Text, Title, Box } from '@mantine/core'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import LoginOptions from '@/components/auth/LoginOptions'

export function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <Stack gap={0} mih="100dvh">
      <Group
        component="nav"
        aria-label="Public navigation"
        justify="space-between"
        wrap="nowrap"
        px={{ base: 'xs', sm: 'md' }}
        h={52}
        style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-surface)' }}
      >
        <Button component={Link} to="/" variant="subtle" size="sm" px={6} aria-label="NoLift home" style={{ minHeight: 44 }}>
          <Activity size={19} />
        </Button>
        <Group gap={2} wrap="nowrap">
          <Button component={Link} to="/" variant="subtle" size="xs" px={7} style={{ minHeight: 44 }}>Home</Button>
          <Button component={Link} to="/profiles" variant="subtle" size="xs" px={7} style={{ minHeight: 44 }}>Search</Button>
          <Button component={Link} to="/about" variant="subtle" size="xs" px={7} style={{ minHeight: 44 }}>About</Button>
          <Button component={Link} to="/login" variant="light" size="xs" px={7} style={{ minHeight: 44 }}>Sign in</Button>
        </Group>
      </Group>
      <Box component="main" style={{ flex: 1 }}>{children}</Box>
    </Stack>
  )
}

export default function LandingPage() {
  return (
    <Center mih="calc(100dvh - 60px)" py="md">
      <Container size="md" w="100%">
        <Stack gap="lg">
          <Stack gap="xs">
            <Group gap="xs">
              <Activity size={22} color="var(--accent-blue)" />
              <Text fw={700} size="sm" tt="uppercase" c="dimmed" style={{ letterSpacing: '0.12em' }}>
                NoLift Training
              </Text>
            </Group>
            <Title order={1} size="h2">
              Train with a plan. Peak with proof.
            </Title>
            <Text c="dimmed" maw={620} size="sm">
              Sessions, readiness, and meet targets in one focused place.
            </Text>
          </Stack>

          <Paper withBorder shadow="sm" radius="md" p={{ base: 'md', sm: 'lg' }}>
            <Stack gap="sm">
              <Text fw={700}>Sign in to continue</Text>
              <LoginOptions compact />
              <Group gap="xs" align="flex-start" wrap="nowrap">
                <ShieldCheck size={16} color="var(--accent-blue)" style={{ flex: '0 0 auto', marginTop: 2 }} />
                <Text size="xs" c="dimmed">
                  Personal training data stays private and separate from public profiles.
                </Text>
              </Group>
            </Stack>
          </Paper>

          <Group justify="center" gap="xs">
            <Button component={Link} to="/profiles" variant="subtle" size="sm" leftSection={<Search size={15} />}>
              Search profiles
            </Button>
            <Button component={Link} to="/about" variant="subtle" size="sm">
              About NoLift
            </Button>
          </Group>
        </Stack>
      </Container>
    </Center>
  )
}
