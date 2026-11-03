import { Link } from 'react-router-dom'
import { Card, SimpleGrid, Text, UnstyledButton, Group, Stack } from '@mantine/core'
import { Calculator, ActivitySquare, Scale, Percent, ArrowRightLeft, Trophy } from 'lucide-react'

export default function ToolsPage() {
  const tools = [
    { to: '/tools/plate', icon: Calculator, title: 'Plate Calc', desc: 'Calculate the plates you need for your target weight.' },
    { to: '/tools/dots', icon: ActivitySquare, title: 'DOTS', desc: 'Calculate your DOTS score for powerlifting competitions.' },
    { to: '/tools/weight', icon: Scale, title: 'Weight Tracker', desc: 'Track your body weight and view your progress.' },
    { to: '/tools/percent', icon: Percent, title: '% of Max', desc: 'Calculate percentages of your 1RM for different lifts.' },
    { to: '/tools/converter', icon: ArrowRightLeft, title: 'Unit Converter', desc: 'Convert weights between kilograms and pounds.' },
    { to: '/tools/attempts', icon: Trophy, title: 'Attempt Selector', desc: 'Plan your competition attempts based on projected maxes.' },
    { to: '/rankings', icon: Trophy, title: 'Rankings', desc: 'Browse OpenPowerlifting rankings and find lifters.' },
  ]

  return (
    <Stack gap="md">
      <Text size="xl" fw={700}>Tools</Text>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {tools.map((tool) => (
          <UnstyledButton key={tool.to} component={Link} to={tool.to} data-testid={`tools-link-${tool.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
            <Card withBorder shadow="sm" padding="lg">
              <Stack justify="space-between" h="100%">
                <div>
                  <Group gap="sm" mb="sm">
                    <tool.icon size={24} />
                    <Text size="lg" fw={600}>{tool.title}</Text>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {tool.desc}
                  </Text>
                </div>
                <Text size="xs" c="blue" mt="md">Open tool →</Text>
              </Stack>
            </Card>
          </UnstyledButton>
        ))}
      </SimpleGrid>
    </Stack>
  )
}
