import { useEffect } from 'react'
import {
  Avatar,
  Button,
  Drawer,
  Group,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { useUiStore } from '@/store/uiStore'
import { defaultBarWeightKgForUnit, useSettingsStore, type Theme } from '@/store/settingsStore'
import { useProgramStore } from '@/store/programStore'
import { useAuth } from '@/auth/AuthProvider'
import { fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { WEEK_START_DAYS, weekStartForBlock } from '@/utils/weekStart'
import { LogIn, LogOut } from 'lucide-react'
import type { Sex, WeekStartDay } from '@powerlifting/types'

const themeOptions: { value: Theme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
]

function SectionLabel({ children }: { children: string }) {
  return (
    <Text className="if-card-title" mb="xs">
      {children}
    </Text>
  )
}

export default function SettingsDrawer() {
  const { drawerOpen, drawerType, closeDrawer } = useUiStore()
  const {
    unit,
    theme,
    setTheme,
    sex,
    setSex,
    barWeightKg,
    setBarWeight,
    defaultSessionsView, setDefaultSessionsView,
  } = useSettingsStore()
  const { program, setSex: programSetSex, setWeekStartDay } = useProgramStore()
  const { user, loading, readOnly, signIn, signOut } = useAuth()

  const isOpen = drawerOpen && drawerType === 'settings'
  const effectiveSex = program?.meta?.sex ?? sex

  useEffect(() => {
    const programSex = program?.meta?.sex
    if (programSex && programSex !== sex) {
      setSex(programSex)
    }
  }, [program?.meta?.sex, setSex, sex])

  return (
    <Drawer
      opened={isOpen}
      onClose={closeDrawer}
      title="Settings"
      position="right"
      size="sm"
      shadow="md"
      styles={{
        content: {
          background: 'var(--bg-surface)',
          color: 'var(--text-primary)',
        },
        header: {
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
        },
      }}
    >
      <Stack gap="xl">
        {/* Authentication */}
        <div>
          <SectionLabel>Account</SectionLabel>
          {loading ? (
            <Text size="xs" c="dimmed">Loading account...</Text>
          ) : user ? (
            <Stack gap="xs">
              <Group gap="sm">
                <Avatar
                  src={user.avatar}
                  alt={user.username}
                  size={32}
                  radius="xl"
                >
                  {user.username[0]?.toUpperCase()}
                </Avatar>
                <Stack gap={0}>
                  <Text size="sm" fw={600}>{user.username}</Text>
                  <Text size="xs" c="dimmed">Discord User</Text>
                </Stack>
              </Group>
              <Button
                variant="light"
                color="red"
                size="sm"
                leftSection={<LogOut size={16} />}
                onClick={signOut}
                fullWidth
              >
                Sign out
              </Button>
            </Stack>
          ) : (
            <Button
              variant="filled"
              size="sm"
              leftSection={<LogIn size={16} />}
              onClick={signIn}
              fullWidth
            >
              Sign in with Discord
            </Button>
          )}
        </div>

        {/* Theme */}
        <div>
          <SectionLabel>Appearance</SectionLabel>
          <SegmentedControl
            value={theme}
            onChange={(value) => setTheme(value as Theme)}
            data={themeOptions}
            fullWidth
            className="if-segmented"
          />
        </div>

        {/* Sessions View */}
        <div>
          <SectionLabel>Preferences</SectionLabel>
          <Text size="sm" fw={500} mb="xs">Default Sessions View</Text>
          <Select
            value={defaultSessionsView}
            onChange={(val) => val && setDefaultSessionsView(val as 'Month' | 'Agenda' | 'Compact')}
            data={[
              { label: 'Agenda', value: 'Agenda' },
              { label: 'Month', value: 'Month' },
              { label: 'Compact', value: 'Compact' },
            ]}
            data-testid="settings-default-sessions-view"
          />
        </div>

        {/* Sex for DOTS calculation */}
        <div>
          <Text size="sm" fw={500} mb="xs">Sex (for DOTS calculation)</Text>
          <SegmentedControl
            value={effectiveSex}
            onChange={(val) => {
              const newSex = val as Sex
              setSex(newSex)
              if (program) programSetSex(newSex).catch(console.error)
            }}
            data={[
              { label: 'Male', value: 'male' },
              { label: 'Female', value: 'female' },
            ]}
            fullWidth
            className="if-segmented"
            disabled={readOnly}
            data-testid="settings-sex"
          />
        </div>

        <div>
          <Text size="sm" fw={500} mb="xs">
            Training Week Start
          </Text>
          <Select
            value={weekStartForBlock(program, 'current')}
            onChange={(value) => value && setWeekStartDay(value as WeekStartDay).catch(console.error)}
            data={WEEK_START_DAYS.map((day) => ({ value: day, label: day }))}
            disabled={readOnly}
            data-testid="settings-week-start"
          />
        </div>

        {/* Bar Weight */}
        <div>
          <Text size="sm" fw={500} mb="xs">
            Bar Weight ({unit})
          </Text>
          <TextInput
            type="number"
            value={toDisplayUnit(barWeightKg, unit)}
            onChange={(e) => setBarWeight(
              e.currentTarget.value !== ''
                ? fromDisplayUnit(Number(e.currentTarget.value), unit)
                : defaultBarWeightKgForUnit(unit),
            )}
            step={unit === 'kg' ? 0.25 : 0.5}
            disabled={readOnly}
            data-testid="settings-bar-weight"
          />
          <Text size="xs" c="dimmed" mt={4}>
            Used for plate calculator. Default is 20kg in metric mode and 45lb in imperial mode.
          </Text>
        </div>
      </Stack>
    </Drawer>
  )
}
