import { useEffect, useState } from 'react'
import {
  ActionIcon,
  Box,
  Button,
  Group,
  Modal,
  Text,
} from '@mantine/core'
import { Minus, Plus } from 'lucide-react'
import { formatRestMs, useRestTimerStore } from '@/store/restTimerStore'

const DEFAULT_SECONDS = 120
const STEP_SECONDS = 15
const MIN_SECONDS = 15
const MAX_SECONDS = 600

export default function RestTimerDialog() {
  const dialogOpen = useRestTimerStore((s) => s.dialogOpen)
  const closeDialog = useRestTimerStore((s) => s.closeDialog)
  const totalSeconds = useRestTimerStore((s) => s.totalSeconds)
  const start = useRestTimerStore((s) => s.start)

  const [seconds, setSeconds] = useState(DEFAULT_SECONDS)

  useEffect(() => {
    if (dialogOpen) {
      setSeconds(totalSeconds >= MIN_SECONDS ? totalSeconds : DEFAULT_SECONDS)
    }
  }, [dialogOpen, totalSeconds])

  const dec = () => setSeconds((s) => Math.max(MIN_SECONDS, s - STEP_SECONDS))
  const inc = () => setSeconds((s) => Math.min(MAX_SECONDS, s + STEP_SECONDS))

  const handleStart = () => {
    start(seconds)
    closeDialog()
  }

  return (
    <Modal
      opened={dialogOpen}
      onClose={closeDialog}
      title="Rest timer"
      centered
      size="sm"
    >
      <Group justify="center" align="center" gap="xl" my="xl">
        <ActionIcon
          size={56}
          radius="xl"
          variant="default"
          onClick={dec}
          aria-label={`Subtract ${STEP_SECONDS} seconds`}
        >
          <Minus size={24} />
        </ActionIcon>

        <Box
          style={{
            width: 160,
            height: 160,
            borderRadius: '50%',
            border: '2px solid var(--border-default)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-elevated)',
          }}
        >
          <Text
            fw={700}
            style={{
              fontSize: 44,
              lineHeight: 1,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {formatRestMs(seconds * 1000)}
          </Text>
        </Box>

        <ActionIcon
          size={56}
          radius="xl"
          variant="default"
          onClick={inc}
          aria-label={`Add ${STEP_SECONDS} seconds`}
        >
          <Plus size={24} />
        </ActionIcon>
      </Group>

      <Group justify="flex-end" gap="sm">
        <Button variant="default" onClick={closeDialog}>
          Cancel
        </Button>
        <Button onClick={handleStart} size="md">
          Start
        </Button>
      </Group>
    </Modal>
  )
}