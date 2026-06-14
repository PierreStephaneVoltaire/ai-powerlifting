import { Link } from 'react-router-dom'
import { Card, SimpleGrid, Text, UnstyledButton, Group, Stack } from '@mantine/core'
import { GitBranch, ClipboardList, BookOpen, Trophy, Import, Target, Shield } from 'lucide-react'

export default function DesignerLanding() {
  return (
    <Stack gap="md">
      <Text size="xl" fw={700}>Program Designer</Text>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        <UnstyledButton component={Link} to="/designer/phases">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <GitBranch size={24} />
                  <Text size="lg" fw={600}>Phase Design</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Manage training phases, set week ranges and RPE targets, and organize your training blocks.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open phase designer →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/sessions">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <ClipboardList size={24} />
                  <Text size="lg" fw={600}>Session Design</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Plan and manage training sessions by week, add exercises, and set planned sets and reps.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open session designer →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/templates">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <BookOpen size={24} />
                  <Text size="lg" fw={600}>Templates</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Manage reusable training templates. Create, apply, or evaluate program structures.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open template library →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/import">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <Import size={24} />
                  <Text size="lg" fw={600}>Import</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Import logs, template spreadsheets, or custom formats into your program.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open import wizard →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/glossary">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <BookOpen size={24} />
                  <Text size="lg" fw={600}>Glossary</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Manage exercise names, primary muscle groups, categories, and video links.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open glossary →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/competitions">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <Trophy size={24} />
                  <Text size="lg" fw={600}>Competitions</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Plan your competitions, track results, and project attempt selections.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open competitions →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/goals">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <Target size={24} />
                  <Text size="lg" fw={600}>Goals</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Define block-wide goals, competition intent, qualifying targets, and weight-class options.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open goals →</Text>
            </Stack>
          </Card>
        </UnstyledButton>

        <UnstyledButton component={Link} to="/designer/federations">
          <Card withBorder shadow="sm" padding="lg">
            <Stack justify="space-between" h="100%">
              <div>
                <Group gap="sm" mb="sm">
                  <Shield size={24} />
                  <Text size="lg" fw={600}>Federations</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Keep a reusable library of federations and manual qualification standards for meet planning.
                </Text>
              </div>
              <Text size="xs" c="blue" mt="md">Open federations →</Text>
            </Stack>
          </Card>
        </UnstyledButton>
      </SimpleGrid>
    </Stack>
  )
}
