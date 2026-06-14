import React, { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Container, LoadingOverlay } from '@mantine/core'
import { fetchTemplate } from '../api/client'
import { TemplateDetail } from '../components/templates/TemplateDetail'
import type { Template } from '@powerlifting/types'
import { useAuth } from '@/auth/AuthProvider'

export default function TemplateDetailPage() {
  const { readOnly } = useAuth()
  const { sk } = useParams<{ sk: string }>()
  const [searchParams] = useSearchParams()
  const resolvedSk = sk ?? searchParams.get('sk') ?? undefined
  const [template, setTemplate] = useState<Template | null>(null)
  const [loading, setLoading] = useState(true)

  const loadTemplate = () => {
    if (resolvedSk) {
      setLoading(true)
      fetchTemplate(resolvedSk)
        .then(setTemplate)
        .catch(() => setTemplate(null))
        .finally(() => setLoading(false))
    } else {
      setTemplate(null)
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTemplate()
  }, [resolvedSk])

  if (!template && !loading) return <div>Template not found</div>

  return (
    <Container size="lg" py="xl">
      <LoadingOverlay visible={loading} />
      {template && (
        <TemplateDetail
          template={template}
          templateSk={resolvedSk}
          onRefresh={loadTemplate}
          readOnly={readOnly}
        />
      )}
    </Container>
  )
}
