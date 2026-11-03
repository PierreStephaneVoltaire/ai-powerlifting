import React from 'react'
import { SimpleGrid, Card, Text, Button, Stack, Badge } from '@mantine/core'
import type { ImportType } from '@powerlifting/types'

interface Props {
  selected: ImportType | null
  onPick: (choice: ImportType) => void
}

export const AmbiguityResolver: React.FC<Props> = ({ selected, onPick }) => {
  return (
    <Stack py="md">
      <Text fw={500} size="sm" c="dimmed">
        We couldn't automatically determine the file type. Please choose:
      </Text>
      <SimpleGrid cols={2} spacing="md">
        <Card
          withBorder
          radius="md"
          padding="lg"
          style={{
            borderColor: selected === 'template' ? 'var(--mantine-color-blue-6)' : undefined,
            borderWidth: selected === 'template' ? 2 : 1,
          }}
        >
          <Stack align="center" gap="sm">
            <Badge color="blue" size="lg">Reusable Template</Badge>
            <Text size="sm" ta="center" c="dimmed">
              Relative weeks/days, RPE or %-based loads, no calendar dates. Goes
              into your Template Library.
            </Text>
            <Button
              variant={selected === 'template' ? 'filled' : 'outline'}
              color="blue"
              onClick={() => onPick('template')}
              fullWidth
            >
              Treat as Template
            </Button>
          </Stack>
        </Card>

        <Card
          withBorder
          radius="md"
          padding="lg"
          style={{
            borderColor: selected === 'session_import' ? 'var(--mantine-color-green-6)' : undefined,
            borderWidth: selected === 'session_import' ? 2 : 1,
          }}
        >
          <Stack align="center" gap="sm">
            <Badge color="green" size="lg">Session Log</Badge>
            <Text size="sm" ta="center" c="dimmed">
              Calendar dates and absolute kg values. Gets merged into your
              training history as a new program version.
            </Text>
            <Button
              variant={selected === 'session_import' ? 'filled' : 'outline'}
              color="green"
              onClick={() => onPick('session_import')}
              fullWidth
            >
              Treat as Session Log
            </Button>
          </Stack>
        </Card>
      </SimpleGrid>
    </Stack>
  )
}
