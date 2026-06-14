import { Link } from 'react-router-dom'
import { SimpleGrid, Stack, Text, UnstyledButton } from '@mantine/core'
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
    <Stack gap="md" className="if-mock-page" data-testid="log-page">
      <div className="if-mock-header" style={{ alignItems: 'flex-start' }}>
        <div>
          <h1 className="if-mock-title">Log</h1>
          <div className="if-mock-subtitle">Quick entry points for notes, supplements, and biometrics.</div>
        </div>
      </div>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {LOG_ITEMS.map((item) => (
          <UnstyledButton key={item.to} component={Link} to={item.to} data-testid={`log-link-${item.title.toLowerCase()}`}>
            <div className="if-mock-card" style={{ minHeight: 132 }}>
              <item.icon size={18} style={{ color: 'var(--color-text-secondary)', marginBottom: 16 }} />
              <div style={{ color: 'var(--color-text-primary)', fontSize: 15, fontWeight: 500, marginBottom: 4 }}>{item.title}</div>
              <Text size="sm" c="dimmed" lh={1.45}>{item.desc}</Text>
              <div style={{ color: 'var(--color-text-info)', fontSize: 11, marginTop: 16 }}>Open {item.title.toLowerCase()} -&gt;</div>
            </div>
          </UnstyledButton>
        ))}
      </SimpleGrid>
    </Stack>
  )
}
