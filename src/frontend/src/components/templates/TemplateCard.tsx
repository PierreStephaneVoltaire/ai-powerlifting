import React from 'react'
import { Card, Text, Group, Badge, Button, Stack } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import type { TemplateListEntry } from '@powerlifting/types'
import { templateDetailRoute } from '../../utils/templateRoutes'

interface Props {
  template: TemplateListEntry
}

export const TemplateCard: React.FC<Props> = ({ template }) => {
  const navigate = useNavigate()

  return (
    <Card withBorder padding="lg" radius="md">
      <Group justify="space-between" mb="xs">
        <Text fw={500}>{template.name}</Text>
        <Group gap={6}>
          {template.published === false && <Badge color="yellow">Draft</Badge>}
          {template.archived && <Badge color="gray">Archived</Badge>}
        </Group>
      </Group>

      <Stack gap="xs" mb="md">
        <Text size="sm" c="dimmed">
          {template.estimated_weeks} weeks • {template.days_per_week} days/week
        </Text>
        <Text size="xs" c="dimmed">
          Created: {new Date(template.created_at).toLocaleDateString()}
        </Text>
        {template.author && (
          <Text size="xs" c="dimmed">
            Author: {template.author}
          </Text>
        )}
      </Stack>

      <Group grow>
        <Button variant="light" onClick={() => navigate(templateDetailRoute(template.sk))}>
          View Detail
        </Button>
      </Group>
    </Card>
  )
}
