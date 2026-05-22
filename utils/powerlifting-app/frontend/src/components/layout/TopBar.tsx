import { Button, Group } from '@mantine/core'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { Settings } from 'lucide-react'

export default function TopBar() {
  const { unit, toggleUnit } = useSettingsStore()
  const { openDrawer } = useUiStore()

  return (
    <Group justify="flex-end" h="100%" px="md" data-testid="topbar">
      <Group gap="xs">
        <Button variant="subtle" size="sm" onClick={toggleUnit} data-testid="unit-toggle">
          {unit.toUpperCase()}
        </Button>

        <Button
          variant="subtle"
          size="sm"
          aria-label="Settings"
          onClick={() => openDrawer('settings')}
          data-testid="settings-button"
        >
          <Settings size={20} />
        </Button>
      </Group>
    </Group>
  )
}
