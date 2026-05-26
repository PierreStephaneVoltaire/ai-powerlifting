import React from 'react'
import { ImportWizard } from '../components/import/ImportWizard'
import { useAuth } from '@/auth/AuthProvider'

export default function ImportWizardPage() {
  const { readOnly } = useAuth()
  return <ImportWizard readOnly={readOnly} />
}
