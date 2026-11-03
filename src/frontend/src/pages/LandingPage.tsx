import { Activity, Info, Search, ShieldCheck, User } from 'lucide-react'
import { Button, Center, Container, Group, Paper, SimpleGrid, Stack, Text, Title, Box } from '@mantine/core'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

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
      <Box component="main" px={{ base: 'md', sm: 'lg' }} py={{ base: 'md', sm: 'lg' }} maw={1280} mx="auto" w="100%" style={{ flex: 1 }}>{children}</Box>
    </Stack>
  )
}

const EXAMPLE_HANDLE = 'failure'

export default function LandingPage() {
  return (
    <Center mih="calc(100dvh - 140px)">
      <Container size="md" w="100%" px={0}>
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

          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Paper withBorder shadow="sm" radius="md" p={{ base: 'md', sm: 'lg' }}>
              <Stack gap="sm" h="100%">
                <Group gap="xs">
                  <Search size={18} color="var(--accent-blue)" />
                  <Text fw={700}>Search profiles</Text>
                </Group>
                <Text size="sm" c="dimmed" style={{ flex: 1 }}>
                  Browse public Athletes and Coaches by name, federation, role, or tag.
                </Text>
                <Group gap="xs">
                  <Button component={Link} to="/profiles" leftSection={<Search size={15} />}>
                    Search
                  </Button>
                  <Button component={Link} to={`/profiles?q=${EXAMPLE_HANDLE}`} variant="default" leftSection={<User size={15} />}>
                    Example: @{EXAMPLE_HANDLE}
                  </Button>
                </Group>
              </Stack>
            </Paper>

            <Paper withBorder shadow="sm" radius="md" p={{ base: 'md', sm: 'lg' }}>
              <Stack gap="sm" h="100%">
                <Group gap="xs">
                  <Info size={18} color="var(--accent-blue)" />
                  <Text fw={700}>About NoLift</Text>
                </Group>
                <Text size="sm" c="dimmed" style={{ flex: 1 }}>
                  A meet-prep notebook: programs, sessions, attempts, and competition planning anchored to your next meet.
                </Text>
                <Group gap="xs">
                  <Button component={Link} to="/about" variant="default">
                    Learn more
                  </Button>
                </Group>
              </Stack>
            </Paper>
          </SimpleGrid>

          <Group gap="xs" justify="center" wrap="nowrap">
            <ShieldCheck size={16} color="var(--accent-blue)" style={{ flex: '0 0 auto' }} />
            <Text size="xs" c="dimmed">
              Personal training data stays private unless an Athlete publishes it.
            </Text>
          </Group>
        </Stack>
      </Container>
    </Center>
  )
}
