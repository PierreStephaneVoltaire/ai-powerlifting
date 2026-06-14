import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { AlertCircle, BookOpen, CalendarDays, Dumbbell, LogIn, PencilRuler } from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'
import { fetchTemplates } from '@/api/client'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import type { TemplateListEntry, WeekStartDay } from '@powerlifting/types'

const WEEK_START_OPTIONS: WeekStartDay[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

const todayIso = () => new Date().toISOString().slice(0, 10)

function maxLabel(id: string): string {
  const labels: Record<string, string> = {
    squat: 'Squat',
    bench: 'Bench',
    deadlift: 'Deadlift',
  }
  return labels[id] ?? id.replace(/[_-]/g, ' ')
}

interface SetupOnboardingProps {
  compact?: boolean
}

export default function SetupOnboarding({ compact = false }: SetupOnboardingProps) {
  const navigate = useNavigate()
  const { user, readOnly, signIn } = useAuth()
  const { initializeSetup, loadProgram, loadVersions } = useProgramStore()
  const { pushToast } = useUiStore()
  const [programName, setProgramName] = useState('Getting Started')
  const [startDate, setStartDate] = useState(todayIso())
  const [weekStartDay, setWeekStartDay] = useState<WeekStartDay>('Monday')
  const [templates, setTemplates] = useState<TemplateListEntry[]>([])
  const [templateSk, setTemplateSk] = useState<string | null>(null)
  const [missingMaxes, setMissingMaxes] = useState<string[]>([])
  const [maxValues, setMaxValues] = useState<Record<string, string>>({})
  const [loadingMode, setLoadingMode] = useState<'blank' | 'manual_sessions' | 'template' | null>(null)

  useEffect(() => {
    if (readOnly) return
    fetchTemplates()
      .then((items) => {
        setTemplates(items)
        setTemplateSk(items[0]?.sk ?? null)
      })
      .catch(() => setTemplates([]))
  }, [readOnly])

  const templateOptions = useMemo(
    () => templates.map((template) => ({
      value: template.sk,
      label: template.name || template.sk,
    })),
    [templates],
  )

  const maxPayload = useMemo(() => {
    const entries = Object.entries(maxValues)
      .map(([key, value]) => [key, Number(value)] as const)
      .filter(([, value]) => Number.isFinite(value) && value > 0)
    return Object.fromEntries(entries)
  }, [maxValues])

  const handleInitialize = async (mode: 'blank' | 'manual_sessions' | 'template') => {
    if (mode === 'template' && !templateSk) {
      pushToast({ message: 'Choose a template first', type: 'error' })
      return
    }

    setLoadingMode(mode)
    try {
      const result = await initializeSetup({
        mode,
        programName,
        startDate,
        weekStartDay,
        ...(mode === 'template' && templateSk ? { templateSk } : {}),
        ...(Object.keys(maxPayload).length > 0 ? { maxes: maxPayload } : {}),
      })

      if (result.status === 'gate_blocked') {
        setMissingMaxes(result.missingMaxes ?? [])
        pushToast({ message: 'Enter estimated maxes to apply this template', type: 'error' })
        return
      }

      await loadProgram('current')
      await loadVersions()
      pushToast({ message: 'Training block initialized', type: 'success' })

      if (mode === 'manual_sessions') {
        navigate('/designer/sessions')
      } else if (mode === 'template') {
        navigate('/sessions')
      } else {
        navigate('/')
      }
    } catch (err) {
      pushToast({ message: 'Setup failed', type: 'error' })
    } finally {
      setLoadingMode(null)
    }
  }

  if (readOnly || !user) {
    return (
      <Paper withBorder p="lg">
        <Stack gap="md" align="flex-start">
          <Group gap="xs">
            <Dumbbell size={22} />
            <Title order={compact ? 3 : 2}>Set Up Training Data</Title>
          </Group>
          <Text c="dimmed" maw={720}>
            This account is viewing the public operator dataset. Sign in to create a private training block.
          </Text>
          <Button leftSection={<LogIn size={16} />} onClick={signIn}>Sign in</Button>
        </Stack>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="lg">
      <Stack gap="lg">
        <Stack gap={4}>
          <Group gap="xs">
            <Dumbbell size={22} />
            <Title order={compact ? 3 : 2}>Set Up Your First Block</Title>
          </Group>
          <Text c="dimmed" maw={760}>
            Start with an empty block now, design sessions manually, or apply a template.
          </Text>
        </Stack>

        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
          <TextInput
            label="Block name"
            value={programName}
            onChange={(event) => setProgramName(event.currentTarget.value)}
          />
          <TextInput
            label="Start date"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.currentTarget.value)}
          />
          <Select
            label="Week starts"
            value={weekStartDay}
            data={WEEK_START_OPTIONS}
            onChange={(value) => setWeekStartDay((value as WeekStartDay | null) ?? 'Monday')}
          />
        </SimpleGrid>

        {missingMaxes.length > 0 && (
          <Alert color="yellow" variant="light" icon={<AlertCircle size={16} />} title="Template maxes needed">
            <Stack gap="xs" mt="xs">
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                {missingMaxes.map((id) => (
                  <TextInput
                    key={id}
                    label={`${maxLabel(id)} e1RM`}
                    type="number"
                    value={maxValues[id] ?? ''}
                    onChange={(event) => setMaxValues((current) => ({
                      ...current,
                      [id]: event.currentTarget.value,
                    }))}
                    rightSection={<Text size="xs" c="dimmed">kg</Text>}
                  />
                ))}
              </SimpleGrid>
            </Stack>
          </Alert>
        )}

        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
          <Button
            leftSection={<CalendarDays size={16} />}
            variant="filled"
            loading={loadingMode === 'blank'}
            onClick={() => handleInitialize('blank')}
          >
            Start blank block
          </Button>
          <Button
            leftSection={<PencilRuler size={16} />}
            variant="light"
            loading={loadingMode === 'manual_sessions'}
            onClick={() => handleInitialize('manual_sessions')}
          >
            Design sessions manually
          </Button>
          <Stack gap="xs">
            <Select
              placeholder={templates.length ? 'Choose template' : 'No templates available'}
              data={templateOptions}
              value={templateSk}
              onChange={setTemplateSk}
              disabled={!templates.length}
            />
            <Button
              leftSection={<BookOpen size={16} />}
              variant="light"
              disabled={!templates.length}
              loading={loadingMode === 'template'}
              onClick={() => handleInitialize('template')}
            >
              Start from template
            </Button>
          </Stack>
        </SimpleGrid>
      </Stack>
    </Paper>
  )
}
