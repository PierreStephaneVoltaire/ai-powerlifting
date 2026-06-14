import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, Center, Loader, Stack, Text } from '@mantine/core'
import { ArrowLeft } from 'lucide-react'
import { useProgramStore } from '@/store/programStore'
import SessionDrawer from '@/components/sessions/SessionDrawer'

export default function SessionDetailPage() {
  const { date, index } = useParams<{ date: string; index?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { program, isLoading } = useProgramStore()
  const fallbackBackTo = location.pathname.startsWith('/list/') ? '/sessions?view=Compact' : '/sessions'
  const backTo = typeof location.state === 'object' && location.state && 'backTo' in location.state
    ? String((location.state as { backTo?: string }).backTo || fallbackBackTo)
    : fallbackBackTo

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
          <Button leftSection={<ArrowLeft size={16} />} variant="default" onClick={() => navigate(backTo)}>
            Back
          </Button>
        </Stack>
      </Alert>
    )
  }

  const parsedIndex = index !== undefined ? Number.parseInt(index, 10) : Number.NaN
  const hasExplicitIndex = Number.isInteger(parsedIndex) && parsedIndex >= 0
  const sessionIndex = hasExplicitIndex
    ? (program.sessions[parsedIndex]?.date === date ? parsedIndex : -1)
    : program.sessions.findIndex((session) => session.date === date)
  const session = sessionIndex >= 0 ? program.sessions[sessionIndex] : null

  if (!session) {
    return (
      <Alert color="yellow" variant="light" title="Session not found">
        <Stack gap="xs">
          <Text size="sm">No session exists for {date}.</Text>
          <Button leftSection={<ArrowLeft size={16} />} variant="default" onClick={() => navigate(backTo)}>
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
        onClose={() => navigate(backTo)}
        onDeleteSuccess={() => navigate(backTo)}
        session={session}
        sessionIndex={sessionIndex}
        sessionArrayIndex={sessionIndex}
        mode="page"
      />
    </Stack>
  )
}
