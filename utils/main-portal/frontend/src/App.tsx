import { Routes, Route } from 'react-router-dom'
import { AppShell, Group, Text } from '@mantine/core'
import { Hub } from './pages/Hub'

export default function App() {
  return (
    <AppShell header={{ height: 52 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Text fw={600} size="lg" ff="var(--font-sans)" c="var(--text-primary)">
            IF Hub
          </Text>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Hub />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  )
}
