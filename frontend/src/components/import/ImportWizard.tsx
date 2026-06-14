import { useReducer, useEffect } from 'react'
import { Stepper, Paper, Title, Stack, Group, Text } from '@mantine/core'
import { useSearchParams, Link } from 'react-router-dom'
import { Step1_Upload } from './Step1_Upload'
import { Step2_Classification } from './Step2_Classification'
import { Step3_GlossaryReview } from './Step3_GlossaryReview'
import { Step4_Preview } from './Step4_Preview'
import { Step6_Apply } from './Step6_Apply'
import { AutoAddReview } from './AutoAddReview'
import type { AutoAddDraft } from './AutoAddReview'
import { fetchPendingImport } from '../../api/client'
import type { ImportPending, ImportType } from '@powerlifting/types'

export interface WizardOverrides {
  classificationOverride: ImportType | null
  glossaryOverrides: Record<string, string> // original name -> glossary_id
  autoAdds: AutoAddDraft[]
}

interface WizardState extends WizardOverrides {
  activeStep: number
  importId: string | null
  pendingImport: ImportPending | null
  loading: boolean
  error: string | null
}

export type WizardAction =
  | { type: 'SET_STEP'; payload: number }
  | { type: 'UPLOAD_SUCCESS'; payload: string }
  | { type: 'IMPORT_LOADED'; payload: ImportPending }
  | { type: 'SET_ERROR'; payload: string }
  | { type: 'CLASSIFICATION_OVERRIDE'; payload: ImportType }
  | { type: 'OVERRIDE_GLOSSARY_MATCH'; payload: { name: string; glossaryId: string } }
  | { type: 'SET_AUTO_ADDS'; payload: AutoAddDraft[] }
  | { type: 'RESET' }

const initialState: WizardState = {
  activeStep: 0,
  importId: null,
  pendingImport: null,
  loading: false,
  error: null,
  classificationOverride: null,
  glossaryOverrides: {},
  autoAdds: [],
}

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'SET_STEP':
      return { ...state, activeStep: action.payload }
    case 'UPLOAD_SUCCESS':
      return { ...state, importId: action.payload, activeStep: 1 }
    case 'IMPORT_LOADED': {
      const autoAddedNames = action.payload.ai_parse_result
        ? (action.payload as any).glossary_resolution?.auto_added || []
        : []
      const autoAdds = (autoAddedNames as string[]).map((n): AutoAddDraft => ({
        name: n,
        category: 'back',
        confirmed: true,
      }))
      return {
        ...state,
        pendingImport: action.payload,
        importId: action.payload.import_id,
        autoAdds: state.autoAdds.length ? state.autoAdds : autoAdds,
      }
    }
    case 'SET_ERROR':
      return { ...state, error: action.payload }
    case 'CLASSIFICATION_OVERRIDE':
      return { ...state, classificationOverride: action.payload }
    case 'OVERRIDE_GLOSSARY_MATCH':
      return {
        ...state,
        glossaryOverrides: {
          ...state.glossaryOverrides,
          [action.payload.name]: action.payload.glossaryId,
        },
      }
    case 'SET_AUTO_ADDS':
      return { ...state, autoAdds: action.payload }
    case 'RESET':
      return initialState
    default:
      return state
  }
}

// Steps: Upload(0) → Classify(1) → Glossary(2) → AutoAdd(3) → Preview(4) → Completed
const STEP_COUNT = 5 // 5 rendered steps → Completed triggers at index 5

export const ImportWizard: React.FC<{ readOnly?: boolean }> = ({ readOnly }) => {
  const [state, dispatch] = useReducer(wizardReducer, initialState)
  const [searchParams, setSearchParams] = useSearchParams()

  useEffect(() => {
    const importId = searchParams.get('import_id')
    if (importId && !state.pendingImport) {
      fetchPendingImport(importId)
        .then(data => {
          dispatch({ type: 'IMPORT_LOADED', payload: data })
          if (data.status === 'awaiting_review') {
            dispatch({ type: 'SET_STEP', payload: 1 })
          }
        })
        .catch(err => dispatch({ type: 'SET_ERROR', payload: err.message }))
    }
  }, [searchParams])

  const nextStep = () =>
    dispatch({ type: 'SET_STEP', payload: state.activeStep + 1 })

  const prevStep = () =>
    dispatch({ type: 'SET_STEP', payload: state.activeStep - 1 })

  return (
    <Stack gap="lg">
      <Group gap="xs">
        <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
          Designer
        </Text>
        <Text c="dimmed">/</Text>
        <Title order={2}>Import Training Program</Title>
      </Group>

      <Paper withBorder p="xl" radius="md">
        <Stepper active={state.activeStep} onStepClick={(step) => dispatch({ type: 'SET_STEP', payload: step })}>
          <Stepper.Step label="Upload" description="Select file">
            <Step1_Upload onUpload={(id) => {
              dispatch({ type: 'UPLOAD_SUCCESS', payload: id })
              setSearchParams({ import_id: id })
            }} readOnly={readOnly} />
          </Stepper.Step>

          <Stepper.Step label="Classify" description="Template vs Log">
            <Step2_Classification
              pendingImport={state.pendingImport}
              classificationOverride={state.classificationOverride}
              onOverride={(c) => dispatch({ type: 'CLASSIFICATION_OVERRIDE', payload: c })}
              onNext={nextStep}
            />
          </Stepper.Step>

          <Stepper.Step label="Glossary" description="Match exercises">
            <Step3_GlossaryReview
              pendingImport={state.pendingImport}
              overrides={state.glossaryOverrides}
              onOverride={(name, glossaryId) =>
                dispatch({ type: 'OVERRIDE_GLOSSARY_MATCH', payload: { name, glossaryId } })
              }
              onNext={nextStep}
              onPrev={prevStep}
            />
          </Stepper.Step>

          <Stepper.Step label="Auto-Add" description="New glossary entries">
            <AutoAddReview
              drafts={state.autoAdds}
              onChange={(drafts) => dispatch({ type: 'SET_AUTO_ADDS', payload: drafts })}
              onNext={nextStep}
              onPrev={prevStep}
            />
          </Stepper.Step>

          <Stepper.Step label="Preview" description="Review data">
            <Step4_Preview
              pendingImport={state.pendingImport}
              onNext={nextStep}
              onPrev={prevStep}
            />
          </Stepper.Step>

          <Stepper.Completed>
            <Step6_Apply
              pendingImport={state.pendingImport}
              overrides={{
                classificationOverride: state.classificationOverride,
                glossaryOverrides: state.glossaryOverrides,
                autoAdds: state.autoAdds,
              }}
              onPrev={prevStep}
              onReset={() => {
                dispatch({ type: 'RESET' })
                setSearchParams({})
              }}
              readOnly={readOnly}
            />
          </Stepper.Completed>
        </Stepper>
      </Paper>
    </Stack>
  )
}
