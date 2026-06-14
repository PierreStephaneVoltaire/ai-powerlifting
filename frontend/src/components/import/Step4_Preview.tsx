import React from 'react'
import { Stack, Button, Group, Alert } from '@mantine/core'
import { Info } from 'lucide-react'
import { TemplatePreview } from './TemplatePreview'
import type { ImportPending } from '@powerlifting/types'

interface Props {
  pendingImport: ImportPending | null
  onNext: () => void
  onPrev: () => void
}

export const Step4_Preview: React.FC<Props> = ({ pendingImport, onNext, onPrev }) => {
  if (!pendingImport) return null

  const { import_type, ai_parse_result } = pendingImport

  return (
    <Stack py="xl">
      {ai_parse_result.warnings?.length > 0 && (
        <Alert icon={<Info size={16} />} title="Import Warnings" color="orange" mb="md">
          {ai_parse_result.warnings.map((w: any, i: number) => (
            <div key={i}>{w.message}</div>
          ))}
        </Alert>
      )}

      {import_type === 'template' ? (
        <TemplatePreview data={ai_parse_result} />
      ) : (
        <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
          Dated log preview not yet implemented.
        </div>
      )}

      <Group justify="space-between" mt="xl">
        <Button variant="outline" onClick={onPrev}>Back</Button>
        <Button onClick={onNext}>Looks Good, Continue</Button>
      </Group>
    </Stack>
  )
}
