import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Alert, Button, Center, Loader, Stack, Text } from '@mantine/core'
import { ArrowLeft } from 'lucide-react'
import { useProgramStore } from '@/store/programStore'
import { sessionIndexForRoute, sessionRoute } from '@/utils/sessionRoute'
import SessionDrawer from '@/components/sessions/SessionDrawer'

export default function SessionDetailPage() {
  const { date, index } = useParams<{ date: string; index?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const { program, isLoading } = useProgramStore()
  const fallbackBackTo = location.pathname.startsWith('/list/') ? '/sessions?view=Compact' : '/sessions'
  const backTo = typeof location.state === 'object' && location.state && 'backTo' in location.state
    ? String((location.state as { backTo?: string }).backTo || fallbackBackTo)
    : fallbackBackTo

  const goBack = () => navigate(backTo, { state: { restoreScrollY: location.state?.backScrollY, expandedWeeks: location.state?.expandedWeeks } })

  if (isLoading || !program) {
    return (
      <Center mih="50vh">
        <Loader />
      </Center>
    )
  }

  if (!date) {
    return (
      <Alert color="red" variant="light" title="Missing session date">
        <Stack gap="xs">
          <Text size="sm">The session detail page needs a date in the URL.</Text>
          <Button leftSection={<ArrowLeft size={16} />} variant="default" onClick={goBack}>
            Back
          </Button>
        </Stack>
      </Alert>
    )
  }

  const sessionIndex = sessionIndexForRoute(program.sessions, date, index, searchParams.get('session'))
  const session = sessionIndex >= 0 ? program.sessions[sessionIndex] : null

  if (!session) {
    return (
      <Alert color="yellow" variant="light" title="Session not found">
        <Stack gap="xs">
          <Text size="sm">Choose a Session for {date}, or return to the calendar.</Text>
          {!searchParams.get('session') && program.sessions.map((candidate, candidateIndex) => candidate.date === date && (
            <Button key={candidate.id ?? candidateIndex} mih={44} variant="default"
              onClick={() => navigate(sessionRoute(candidate, candidateIndex), { replace: true, state: location.state })}>
              {candidate.phase?.name || 'Session'} · {candidateIndex + 1}
            </Button>
          ))}
          <Button leftSection={<ArrowLeft size={16} />} variant="default" onClick={goBack}>
            Back
          </Button>
        </Stack>
      </Alert>
    )
  }

  return (
    <Stack gap="md" maw={1040} mx="auto" w="100%">
      <SessionDrawer
        isOpen
        onClose={goBack}
        onDeleteSuccess={goBack}
        session={session}
        sessionIndex={sessionIndex}
        sessionArrayIndex={sessionIndex}
        mode="page"
      />
    </Stack>
  )
}
