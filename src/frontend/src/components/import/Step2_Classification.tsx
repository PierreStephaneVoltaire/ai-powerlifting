import React from 'react'
import { Stack, Text, Badge, Button, Paper } from '@mantine/core'
import type { ImportPending, ImportType } from '@powerlifting/types'
import { AmbiguityResolver } from './AmbiguityResolver'

interface Props {
  pendingImport: ImportPending | null
  classificationOverride: ImportType | null
  onOverride: (choice: ImportType) => void
  onNext: () => void
}

export const Step2_Classification: React.FC<Props> = ({
  pendingImport,
  classificationOverride,
  onOverride,
  onNext,
}) => {
  if (!pendingImport) return null

  const classification = classificationOverride || pendingImport.classification
  const isAmbiguous =
    pendingImport.classification === 'ambiguous' && !classificationOverride

  if (isAmbiguous) {
    return (
      <Stack py="xl">
        <AmbiguityResolver selected={classificationOverride} onPick={onOverride} />
      </Stack>
    )
  }

  return (
    <Stack py="xl" align="center">
      <Paper withBorder p="lg" radius="md" style={{ width: '100%', maxWidth: 500 }}>
        <Stack align="center" gap="md">
          <Text size="lg" fw={500}>
            {classificationOverride ? 'Classification (manual)' : 'Classification Detected'}
          </Text>

          <Badge size="xl" color={classification === 'template' ? 'blue' : 'green'}>
            {classification === 'template' ? 'Reusable Template' : 'Session Log / Dated Import'}
          </Badge>

          <Text size="sm" c="dimmed" ta="center">
            {classification === 'template'
              ? 'This file contains relative weeks/days and RPE/% based loads. It will be added to your Template Library.'
              : 'This file contains calendar dates and absolute kg values. It will be merged into your training history.'}
          </Text>

          {pendingImport.classification === 'ambiguous' && (
            <Button
              variant="subtle"
              size="xs"
              onClick={() => onOverride(classification === 'template' ? 'session_import' : 'template')}
            >
              Change
            </Button>
          )}

          <Button onClick={onNext} fullWidth mt="md">
            Confirm & Continue
          </Button>
        </Stack>
      </Paper>
    </Stack>
  )
}
