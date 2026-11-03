import { ActionIcon, Tooltip } from '@mantine/core'
import { Timer } from 'lucide-react'
import { formatRestMs, useRestTimerStore } from '@/store/restTimerStore'

export default function RestTimerHeaderButton() {
  const status = useRestTimerStore((s) => s.status)
  const remainingMs = useRestTimerStore((s) => s.remainingMs)
  const openDialog = useRestTimerStore((s) => s.openDialog)

  const isActive = status !== 'idle'
  const isRunning = status === 'running'
  const isPaused = status === 'paused'
  const isFinished = status === 'finished'

  const color = isFinished ? 'green' : isPaused ? 'yellow' : isRunning ? 'blue' : 'gray'
  const label = isFinished
    ? 'Rest complete'
    : isPaused
      ? `Rest paused at ${formatRestMs(remainingMs)}`
      : isRunning
        ? `Resting — ${formatRestMs(remainingMs)} remaining`
        : 'Start rest timer'

  return (
    <Tooltip label={label} openDelay={300}>
      <ActionIcon
        variant={isActive ? 'light' : 'subtle'}
        color={color}
        size="md"
        onClick={openDialog}
        aria-label={label}
        data-testid="rest-timer-header"
        data-status={status}
      >
        <Timer size={16} />
      </ActionIcon>
    </Tooltip>
  )
}