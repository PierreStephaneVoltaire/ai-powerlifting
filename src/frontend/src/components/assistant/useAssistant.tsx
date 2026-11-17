import { useState } from 'react'
import { ActionIcon } from '@mantine/core'
import { Bot } from 'lucide-react'
import AssistantDrawer from './AssistantDrawer'
import type { AssistantContext, AssistantScope } from '@/api/assistant'

export function useAssistant(scope: AssistantScope, context: AssistantContext = {}, readOnly?: boolean, onApplied?: () => Promise<void>) {
  const [opened, setOpened] = useState(false)
  const button = (
    <ActionIcon variant="light" color="grape" size="lg" title="Assistant" aria-label="Assistant" onClick={() => setOpened(true)}>
      <Bot size={18} />
    </ActionIcon>
  )
  const drawer = <AssistantDrawer opened={opened} onClose={() => setOpened(false)} scope={scope} context={context} readOnly={readOnly} onApplied={onApplied} />
  return { button, drawer, open: () => setOpened(true) }
}
