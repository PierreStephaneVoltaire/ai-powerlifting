import { ActionIcon, Box, Group, RingProgress, Text, Tooltip } from '@mantine/core'
import { Play, Pause, Plus, Minus, X, RotateCcw } from 'lucide-react'
import { useRestTimerStore, formatRestMs } from '@/store/restTimerStore'

const STEP_SECONDS = 15

export default function RestTimerBar() {
  const status = useRestTimerStore((s) => s.status)
  const totalSeconds = useRestTimerStore((s) => s.totalSeconds)
  const remainingMs = useRestTimerStore((s) => s.remainingMs)
  const pause = useRestTimerStore((s) => s.pause)
  const resume = useRestTimerStore((s) => s.resume)
  const reset = useRestTimerStore((s) => s.reset)
  const addSeconds = useRestTimerStore((s) => s.addSeconds)
  const start = useRestTimerStore((s) => s.start)
  const openDialog = useRestTimerStore((s) => s.openDialog)

  if (status === 'idle') return null

  const isPaused = status === 'paused'
  const isFinished = status === 'finished'
  const isRunning = status === 'running'

  const totalMs = totalSeconds * 1000
  const elapsedMs = Math.max(0, totalMs - remainingMs)
  const progressPct =
    totalMs > 0 ? Math.min(100, Math.max(0, (elapsedMs / totalMs) * 100)) : 0

  const ringColor = isFinished ? 'green' : isPaused ? 'yellow' : 'blue'
  const timeText = isFinished ? '0:00' : formatRestMs(remainingMs)

  const handleAdd = (delta: number) => {
    if (isFinished) {
      start(totalSeconds + delta)
      return
    }
    addSeconds(delta)
  }

  const handleReset = () => {
    reset()
  }

  const handlePlayPause = () => {
    if (isFinished) {
      start(totalSeconds)
      return
    }
    if (isRunning) pause()
    else resume()
  }

  return (
    <Box
      className="if-rest-timer-bar"
      role="region"
      aria-label="Rest timer"
      data-testid="rest-timer-bar"
      data-status={status}
      onClick={openDialog}
    >
      <Group gap="sm" wrap="nowrap" align="center" justify="space-between" w="100%">
        <Group gap="xs" wrap="nowrap" align="center" style={{ minWidth: 0 }}>
          <RingProgress
            size={48}
            thickness={5}
            roundCaps
            sections={[{ value: progressPct, color: ringColor }]}
            label={
              <Text
                size="xs"
                fw={700}
                ta="center"
                c={ringColor}
                style={{ fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}
              >
                {timeText}
              </Text>
            }
          />
          <Box style={{ minWidth: 0 }}>
            <Text size="xs" c="dimmed" fw={500} lh={1.2}>
              {isFinished ? 'Rest complete' : isPaused ? 'Rest paused' : 'Resting'}
            </Text>
            <Text size="xs" c="dimmed" lh={1.2} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {isFinished
                ? 'Tap to dismiss or set a new time'
                : `${formatRestMs(totalMs)} total`}
            </Text>
          </Box>
        </Group>

        <Group gap={4} wrap="nowrap" onClick={(e) => e.stopPropagation()}>
          <Tooltip label={`−${STEP_SECONDS}s`} openDelay={400}>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={() => handleAdd(-STEP_SECONDS)}
              aria-label={`Subtract ${STEP_SECONDS} seconds`}
              data-testid="rest-timer-minus"
            >
              <Minus size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label={isFinished ? 'Restart' : isRunning ? 'Pause' : 'Resume'} openDelay={400}>
            <ActionIcon
              variant="filled"
              color={ringColor}
              size="xl"
              radius="xl"
              onClick={handlePlayPause}
              aria-label={isFinished ? 'Restart' : isRunning ? 'Pause' : 'Resume'}
              data-testid="rest-timer-play"
            >
              {isFinished ? (
                <RotateCcw size={18} />
              ) : isRunning ? (
                <Pause size={18} />
              ) : (
                <Play size={18} style={{ marginLeft: 2 }} />
              )}
            </ActionIcon>
          </Tooltip>
          <Tooltip label={`+${STEP_SECONDS}s`} openDelay={400}>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={() => handleAdd(STEP_SECONDS)}
              aria-label={`Add ${STEP_SECONDS} seconds`}
              data-testid="rest-timer-plus"
            >
              <Plus size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label={isFinished ? 'Dismiss' : 'Reset'} openDelay={400}>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={handleReset}
              aria-label={isFinished ? 'Dismiss timer' : 'Reset timer'}
              data-testid="rest-timer-reset"
            >
              <X size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>
    </Box>
  )
}