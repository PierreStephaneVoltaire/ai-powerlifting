import { Link } from 'react-router-dom'
import { Card, Group, SimpleGrid, Stack, Text, Title, UnstyledButton } from '@mantine/core'
import { BookOpen, Pill, Utensils } from 'lucide-react'

const LOG_ITEMS = [
  {
    to: '/notes',
    icon: BookOpen,
    title: 'Notes',
    desc: 'Dated training context for block exports and analysis.',
  },
  {
    to: '/supplements',
    icon: Pill,
    title: 'Supplements',
    desc: 'Supplement phases, protocol notes, and peak-week details.',
  },
  {
    to: '/biometrics',
    icon: Utensils,
    title: 'Biometrics',
    desc: 'Nutrition, sleep, bodyweight, and recovery snapshots.',
  },
]

export default function LogPage() {
  return (
    <Stack gap="md" data-testid="log-page">
      <Title order={2}>Log</Title>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {LOG_ITEMS.map((item) => (
          <UnstyledButton key={item.to} component={Link} to={item.to} data-testid={`log-link-${item.title.toLowerCase()}`}>
            <Card withBorder shadow="sm" padding="lg">
              <Stack justify="space-between" h="100%">
                <div>
                  <Group gap="sm" mb="sm">
                    <item.icon size={24} />
                    <Text size="lg" fw={600}>{item.title}</Text>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {item.desc}
                  </Text>
                </div>
                <Text size="xs" c="blue" mt="md">Open {item.title.toLowerCase()} -&gt;</Text>
              </Stack>
            </Card>
          </UnstyledButton>
        ))}
      </SimpleGrid>
    </Stack>
  )
}
