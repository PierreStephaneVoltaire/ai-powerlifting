import React, { useState } from 'react'
import { Stack, Group, Title, Button, Text, Badge, Divider, LoadingOverlay, Grid } from '@mantine/core'
import { Edit2, Eye, EyeOff } from 'lucide-react'
import { Template } from '@powerlifting/types'
import { SessionGrid } from './SessionGrid'
import { EvaluationPanel } from './EvaluationPanel'
import { ApplyModal } from './ApplyModal'
import { MaxResolutionGate } from './MaxResolutionGate'
import { confirmApplyTemplate, publishTemplate, unpublishTemplate } from '../../api/client'
import { useNavigate } from 'react-router-dom'
import { templateEditRoute } from '../../utils/templateRoutes'
import { useAuth } from '@/auth/AuthProvider'

interface Props {
  template: Template
  templateSk?: string
  onRefresh: () => void
  readOnly?: boolean
}

export const TemplateDetail: React.FC<Props> = ({ template, templateSk, onRefresh, readOnly }) => {
  const [applyModalOpened, setApplyModalOpened] = useState(false)
  const [missingMaxes, setMissingMaxes] = useState<string[] | null>(null)
  const [applyData, setApplyData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { mapped_pk } = useAuth()
  const resolvedTemplateSk = template.sk || templateSk
  const canEdit = !readOnly && Boolean(resolvedTemplateSk) && template.meta.author_pk === mapped_pk

  const handleApply = async (res: any) => {
    if (res.missing_maxes && res.missing_maxes.length > 0) {
      setMissingMaxes(res.missing_maxes)
      setApplyData(res)
      setApplyModalOpened(false)
    } else {
      if (!resolvedTemplateSk) return
      setLoading(true)
      try {
        const applied = await confirmApplyTemplate(resolvedTemplateSk, {
          start_date: res.start_date,
          week_start_day: res.week_start_day,
          target: res.target,
        })
        navigate(`/designer/sessions?version=${applied.program_sk}`)
      } finally {
        setLoading(false)
      }
    }
  }

  const handlePublishToggle = async () => {
    if (!resolvedTemplateSk || !canEdit) return
    setLoading(true)
    try {
      if (template.meta.published === false) {
        await publishTemplate(resolvedTemplateSk)
      } else {
        await unpublishTemplate(resolvedTemplateSk)
      }
      onRefresh()
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmApply = async (backfilled_maxes: Record<string, number>) => {
    if (!resolvedTemplateSk) return
    setLoading(true)
    try {
      const res = await confirmApplyTemplate(resolvedTemplateSk, {
        backfilled_maxes,
        start_date: applyData.start_date,
        week_start_day: applyData.week_start_day,
        target: applyData.target,
      })
      navigate(`/designer/sessions?version=${res.program_sk}`)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Stack gap="xl">
      <LoadingOverlay visible={loading} />
      <Group justify="space-between">
        <Stack gap={4}>
          <Group gap="sm">
            <Title order={2}>{template.meta.name}</Title>
            {template.meta.published === false && <Badge color="yellow">Draft</Badge>}
            {template.meta.archived && <Badge color="gray">Archived</Badge>}
          </Group>
          <Text size="sm" c="dimmed">
            {template.meta.estimated_weeks} Weeks • {template.meta.days_per_week} Days/Week
          </Text>
        </Stack>
        
        <Group>
          <Button
            variant="default"
            leftSection={template.meta.published === false ? <Eye size={16} /> : <EyeOff size={16} />}
            onClick={handlePublishToggle}
            disabled={!canEdit}
          >
            {template.meta.published === false ? 'Publish' : 'Unpublish'}
          </Button>
          <Button
            variant="default"
            leftSection={<Edit2 size={16} />}
            onClick={() => resolvedTemplateSk && navigate(templateEditRoute(resolvedTemplateSk))}
            disabled={!canEdit}
          >
            Edit
          </Button>
          <Button
            size="lg"
            onClick={() => setApplyModalOpened(true)}
            disabled={!resolvedTemplateSk || readOnly}
          >
            Apply Template
          </Button>
        </Group>
      </Group>

      <Divider />

      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Stack gap="lg">
          <Title order={3}>Sessions</Title>
          <SessionGrid template={template} />
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack gap="lg">
          <Title order={3}>AI Analysis</Title>
          <EvaluationPanel
            sk={resolvedTemplateSk ?? ''}
            evaluation={template.meta.ai_evaluation ?? null}
            onRefresh={onRefresh}
            readOnly={readOnly}
          />          </Stack>
        </Grid.Col>
      </Grid>

      <ApplyModal 
        opened={applyModalOpened} 
        onClose={() => setApplyModalOpened(false)} 
        sk={resolvedTemplateSk ?? ''}
        onApply={handleApply}
      />

      {missingMaxes && (
        <MaxResolutionGate 
          missingMaxes={missingMaxes}
          onResolved={handleConfirmApply}
          onCancel={() => setMissingMaxes(null)}
        />
      )}
    </Stack>
  )
}
