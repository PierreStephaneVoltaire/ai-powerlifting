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
  const routeSession = searchParams.get('session')
  const hasProgram = useProgramStore(s => s.program !== null)
  const sessionIndex = useProgramStore(s => s.program && date ? sessionIndexForRoute(s.program.sessions, date, index, routeSession) : -1)
  const sessionKey = useProgramStore(s => {
    const session = sessionIndex >= 0 ? s.program?.sessions[sessionIndex] : undefined
    return session ? `${s.version}:${session.id || session.date}:${sessionIndex}` : null
  })
  const fallbackBackTo = location.pathname.startsWith('/list/') ? '/sessions?view=Compact' : '/sessions'
  const backTo = typeof location.state === 'object' && location.state && 'backTo' in location.state
    ? String((location.state as { backTo?: string }).backTo || fallbackBackTo)
    : fallbackBackTo

  const goBack = () => navigate(backTo, { state: { restoreScrollY: location.state?.backScrollY, expandedWeeks: location.state?.expandedWeeks } })

  if (!hasProgram) {
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

  if (!sessionKey) {
    const sessions = useProgramStore.getState().program?.sessions ?? []
    return (
      <Alert color="yellow" variant="light" title="Session not found">
        <Stack gap="xs">
          <Text size="sm">Choose a Session for {date}, or return to the calendar.</Text>
          {!routeSession && sessions.map((candidate, candidateIndex) => candidate.date === date && (
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
        key={sessionKey}
        isOpen
        onClose={goBack}
        onDeleteSuccess={goBack}
        sessionIndex={sessionIndex}
        sessionArrayIndex={sessionIndex}
        mode="page"
      />
    </Stack>
  )
}
