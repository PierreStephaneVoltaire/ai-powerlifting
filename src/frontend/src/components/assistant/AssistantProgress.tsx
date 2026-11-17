import { useEffect, useRef, useState } from 'react'
import { Group, Loader, Text, UnstyledButton } from '@mantine/core'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { AssistantProgress as Progress } from '@/api/assistant'

export default function AssistantProgress({ progress, running = false, activity = 'Working' }: { progress?: Progress | null; running?: boolean; activity?: string }) {
  const [open, setOpen] = useState(true)
  const box = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  useEffect(() => {
    if (box.current && pinned.current) box.current.scrollTop = box.current.scrollHeight
  }, [progress?.text, open])

  if (!running && !progress?.text) return null

  return (
    <div>
      <UnstyledButton onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <Group gap="xs" wrap="nowrap">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {running && <Loader size="xs" />}
          <Text size="xs" c="dimmed">{running ? progress?.stage || activity : 'Thinking'}</Text>
        </Group>
      </UnstyledButton>
      {open && progress?.text && (
        <div ref={box} onScroll={(event) => {
          const node = event.currentTarget
          pinned.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48
        }} style={{ maxHeight: '35dvh', overflowY: 'auto', overflowX: 'hidden' }}>
          <Text size="sm" c="dimmed" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{progress.text}</Text>
        </div>
      )}
    </div>
  )
}
