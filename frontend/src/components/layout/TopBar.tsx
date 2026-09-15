import { Button, Group } from '@mantine/core'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { Settings } from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'

export default function TopBar() {
  const { unit, toggleUnit } = useSettingsStore()
  const { openDrawer } = useUiStore()
  const { user, signInDiscord, signInAuthentik } = useAuth()

  return (
    <Group justify="flex-end" h="100%" px="md" data-testid="topbar">
      <Group gap="xs">
        {!user && <>
          <Button variant="light" size="xs" px={5} onClick={signInDiscord} aria-label="Sign in with Discord" style={{ minHeight: 44 }}>Discord</Button>
          <Button variant="default" size="xs" px={5} onClick={signInAuthentik} aria-label="Sign in with Authentik" style={{ minHeight: 44 }}>Authentik</Button>
        </>}
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
