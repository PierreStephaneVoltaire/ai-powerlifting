import React from 'react'
import { Stack, Title, Grid, Card, Text, Group, Badge } from '@mantine/core'
import { LoadTypeBadge } from '../shared/LoadTypeBadge'

interface Props {
  data: any
}

export const TemplatePreview: React.FC<Props> = ({ data }) => {
  const { sessions = [] } = data

  // Group sessions by week
  const weeks: Record<number, any[]> = {}
  sessions.forEach((s: any) => {
    const w = s.week_number || 1
    if (!weeks[w]) weeks[w] = []
    weeks[w].push(s)
  })

  return (
    <Stack gap="xl">
      <Title order={4}>Program Preview</Title>
      
      {Object.keys(weeks).map((wNum) => (
        <Stack key={wNum} gap="md">
          <Text fw={700} size="lg">Week {wNum}</Text>
          <Grid>
            {weeks[Number(wNum)].map((session: any, idx: number) => (
              <Grid.Col key={idx} span={{ base: 12, md: 6, lg: 4 }}>
                <Card withBorder padding="sm" radius="md">
                  <Text fw={500} mb="xs">{session.day_of_week} - {session.label}</Text>
                  <Stack gap={4}>
                    {session.exercises?.map((ex: any, eIdx: number) => (
                      <Group key={eIdx} justify="space-between">
                        <Group gap="xs">
                          <Text size="sm">{ex.name}</Text>
                          <LoadTypeBadge source={ex.load_type} />
                        </Group>
                        <Text size="xs" c="dimmed">
                          {ex.sets}x{ex.reps}
                          {ex.load_type === 'rpe' ? ` @ RPE ${ex.load_value || ex.rpe_target || '?'}` : 
                           ex.load_type === 'percentage' ? ` (${((ex.load_value || 0) * 100).toFixed(0)}%)` :
                           ex.load_value ? ` ${ex.load_value}kg` : ''}
                        </Text>
                      </Group>
                    ))}
                  </Stack>
                </Card>
              </Grid.Col>
            ))}
          </Grid>
        </Stack>
      ))}
    </Stack>
  )
}
