import React from 'react'
import { SimpleGrid, Paper, Text, Stack, Group, Badge } from '@mantine/core'
import { Template } from '@powerlifting/types'
import { LoadTypeBadge } from '../shared/LoadTypeBadge'

interface Props {
  template: Template
}

export const SessionGrid: React.FC<Props> = ({ template }) => {
  const weeks = [...new Set(template.sessions.map(s => s.week_number || 0))].sort((a, b) => a - b)
  
  return (
    <Stack gap="xl">
      {weeks.map(week => {
        const weekSessions = template.sessions
          .filter(s => s.week_number === week)
          .sort((a, b) => (a.day_index || 0) - (b.day_index || 0))
        
        return (
          <Stack key={week} gap="sm">
            <Text fw={700} size="lg">Week {week}</Text>
            <SimpleGrid cols={{ base: 1, md: 2, lg: 3 }}>
              {weekSessions.map((session, idx) => (
                <Paper key={idx} withBorder p="md" radius="md">
                  <Stack gap="xs">
                    <Group justify="space-between">
                      <Text fw={500}>Day {session.day_of_week || '?'}</Text>
                      {session.label && <Badge variant="light">{session.label}</Badge>}
                    </Group>
                    
                    {session.exercises.map((ex, exIdx) => (
                      <Group key={exIdx} justify="space-between" wrap="nowrap" gap="xs">
                        <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
                          <Text size="sm" truncate>{ex.name}</Text>
                          <Text size="xs" c="dimmed">
                            {ex.sets}x{ex.reps}
                            {ex.load_type === 'rpe' && ex.rpe_target != null && ` @ RPE ${ex.rpe_target}`}
                            {ex.load_type === 'percentage' && ex.load_value != null && ` (${(ex.load_value * 100).toFixed(0)}%)`}
                            {ex.load_type === 'absolute' && ex.load_value != null ? ` ${ex.load_value}kg` : ''}
                          </Text>
                        </Stack>
                        {ex.load_type && <LoadTypeBadge source={ex.load_type} />}
                      </Group>
                    ))}
                  </Stack>
                </Paper>
              ))}
            </SimpleGrid>
          </Stack>
        )
      })}
    </Stack>
  )
}
