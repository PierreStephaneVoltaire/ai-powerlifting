import { Routes, Route } from 'react-router-dom'
import { AppShell, Box, Group, Text } from '@mantine/core'
import { FileCheck2 } from 'lucide-react'
import Board from './pages/Board'
import ProposalDetail from './pages/ProposalDetail'

export default function App() {
  return (
    <AppShell
      header={{ height: 56 }}
      padding={0}
      style={{
        background: 'var(--bg-base)',
        color: 'var(--text-primary)',
      }}
    >
      <AppShell.Header
        style={{
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            <Box
              style={{
                width: 28,
                height: 28,
                borderRadius: 6,
                background: 'var(--accent-blue)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <FileCheck2 size={15} color="white" />
            </Box>
            <Text fw={600} size="md" c="var(--text-primary)" truncate>
              Proposals Portal
            </Text>
          </Group>
          <Text size="xs" c="var(--color-text-secondary)" truncate>
            Review, approve, and submit system improvement proposals
          </Text>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Box
          p="md"
          maw={1400}
          mx="auto"
          w="100%"
          style={{ minHeight: 'calc(100dvh - 56px)' }}
        >
          <Routes>
            <Route path="/" element={<Board />} />
            <Route path="/proposal/:sk" element={<ProposalDetail />} />
          </Routes>
        </Box>
      </AppShell.Main>
    </AppShell>
  )
}