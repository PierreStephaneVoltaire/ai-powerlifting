import { useEffect, useState } from 'react'
import { Title, SimpleGrid, Button, Group, LoadingOverlay, Stack, Text } from '@mantine/core'
import { Plus } from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import { fetchTemplates } from '../api/client'
import { TemplateCard } from '../components/templates/TemplateCard'
import type { TemplateListEntry } from '@powerlifting/types'
import { useAuth } from '@/auth/AuthProvider'

export default function TemplateLibraryPage() {
  const { readOnly } = useAuth()
  const [templates, setTemplates] = useState<TemplateListEntry[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    fetchTemplates()
      .then(setTemplates)
      .finally(() => setLoading(false))
  }, [])

  return (
    <Stack gap="lg">
      <LoadingOverlay visible={loading} />
      <Group justify="space-between">
        <Group gap="xs">
          <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
            Designer
          </Text>
          <Text c="dimmed">/</Text>
          <Title order={2}>Template Library</Title>
        </Group>
        <Group gap="xs">
          <Button
            variant="default"
            leftSection={<Plus size={16} />}
            onClick={() => navigate('/designer/templates/new')}
            disabled={readOnly}
          >
            Create Template
          </Button>
          <Button
            leftSection={<Plus size={16} />}
            onClick={() => navigate('/designer/import')}
            disabled={readOnly}
          >
            Import Template
          </Button>
        </Group>
      </Group>

      {templates.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {templates.map(tpl => (
            <TemplateCard key={tpl.sk} template={tpl} />
          ))}
        </SimpleGrid>
      ) : (
        !loading && (
          <Group justify="center" py={48}>
            <Text c="dimmed">No templates found. Import one to get started.</Text>
          </Group>
        )
      )}
    </Stack>
  )
}
