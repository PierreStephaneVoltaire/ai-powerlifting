import { Link } from 'react-router-dom'
import { SimpleGrid, Stack, Text, UnstyledButton } from '@mantine/core'
import { GitBranch, ClipboardList, BookOpen, Trophy, Import, Target, Shield } from 'lucide-react'
import BlockTransitionPanel from '@/components/BlockTransitionPanel'

const items = [
  { to: '/designer/phases', icon: GitBranch, title: 'Phase Design', desc: 'Manage training phases, set week ranges and RPE targets, and organize your training blocks.' },
  { to: '/designer/sessions', icon: ClipboardList, title: 'Session Design', desc: 'Plan and manage training sessions by week, add exercises, and set planned sets and reps.' },
  { to: '/designer/templates', icon: BookOpen, title: 'Templates', desc: 'Manage reusable training templates. Create, apply, or evaluate program structures.' },
  { to: '/designer/import', icon: Import, title: 'Import', desc: 'Import logs, template spreadsheets, or custom formats into your program.' },
  { to: '/designer/glossary', icon: BookOpen, title: 'Glossary', desc: 'Manage exercise names, primary muscle groups, categories, and video links.' },
  { to: '/designer/competitions', icon: Trophy, title: 'Competitions', desc: 'Plan your competitions, track results, and project attempt selections.' },
  { to: '/designer/goals', icon: Target, title: 'Goals', desc: 'Define block-wide goals, competition intent, qualifying targets, and weight-class options.' },
  { to: '/designer/federations', icon: Shield, title: 'Federations', desc: 'Keep a reusable library of federations and manual qualification standards for meet planning.' },
]

export default function DesignerLanding() {
  return (
    <Stack gap="md" className="if-mock-page" data-testid="designer-page">
      <div className="if-mock-header" style={{ alignItems: 'flex-start' }}>
        <div><h1 className="if-mock-title">Program Designer</h1></div>
      </div>
      <BlockTransitionPanel />
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {items.map(({ to, icon: Icon, title, desc }) => (
          <UnstyledButton key={to} component={Link} to={to} style={{ display: 'block', height: '100%' }}>
            <div className="if-mock-card" style={{ boxSizing: 'border-box', height: '100%', minHeight: 132 }}>
              <Icon size={18} style={{ color: 'var(--color-text-secondary)', marginBottom: 16 }} />
              <div style={{ color: 'var(--color-text-primary)', fontSize: 15, fontWeight: 500, marginBottom: 4 }}>{title}</div>
              <Text size="sm" c="dimmed" lh={1.45}>{desc}</Text>
              <div style={{ color: 'var(--color-text-info)', fontSize: 11, marginTop: 16 }}>Open {title.toLowerCase()} →</div>
            </div>
          </UnstyledButton>
        ))}
      </SimpleGrid>
    </Stack>
  )
}
