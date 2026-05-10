import { Drawer, SegmentedControl, Text, Stack, Group, Button, Select, Divider, Avatar, TextInput } from '@mantine/core'
import { useUiStore } from '@/store/uiStore'
import { defaultBarWeightKgForUnit, useSettingsStore, type Theme } from '@/store/settingsStore'
import { useProgramStore } from '@/store/programStore'
import { useAuth } from '@/auth/AuthProvider'
import { fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { WEEK_START_DAYS, weekStartForBlock } from '@/utils/weekStart'
import { Sun, Moon, Monitor, LogIn, LogOut } from 'lucide-react'
import type { WeekStartDay } from '@powerlifting/types'

const themeOptions: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

export default function SettingsDrawer() {
  const { drawerOpen, drawerType, closeDrawer } = useUiStore()
  const {
    unit, theme, setTheme, sex, setSex, barWeightKg, setBarWeight,
    defaultSessionsView, setDefaultSessionsView,
  } = useSettingsStore()
  const { program, setSex: programSetSex, setWeekStartDay } = useProgramStore()
  const { user, loading, signIn, signOut } = useAuth()

  const isOpen = drawerOpen && drawerType === 'settings'

  return (
    <Drawer
      opened={isOpen}
      onClose={closeDrawer}
      title="Settings"
      position="right"
      size="sm"
      shadow="md"
    >
      <Stack gap="lg">
        {/* Authentication */}
        <div>
          <Text size="sm" fw={500} mb="xs">
            Account
          </Text>
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

        <Divider />

        {/* Theme */}
        <div>
          <Text size="sm" fw={500} mb="xs">
            Appearance
          </Text>
          <Group gap="xs">
            {themeOptions.map((option) => {
              const Icon = option.icon
              const active = theme === option.value
              return (
                <Button
                  key={option.value}
                  variant={active ? 'filled' : 'outline'}
                  size="sm"
                  onClick={() => setTheme(option.value)}
                  leftSection={<Icon size={16} />}
                >
                  {option.label}
                </Button>
              )
            })}
          </Group>
        </div>

        {/* Sessions View */}
        <div>
          <Text size="sm" fw={500} mb="xs">
            Default Sessions View
          </Text>
          <Select
            value={defaultSessionsView}
            onChange={(val) => val && setDefaultSessionsView(val as 'Month' | 'Agenda' | 'Compact')}
            data={[
              { label: 'Agenda', value: 'Agenda' },
              { label: 'Month', value: 'Month' },
              { label: 'Compact', value: 'Compact' },
            ]}
          />
        </div>

        {/* Sex for DOTS calculation */}
        <div>
          <Text size="sm" fw={500} mb="xs">
            Sex (for DOTS calculation)
          </Text>
          <SegmentedControl
            value={sex}
            onChange={(val) => {
              const newSex = val as 'male' | 'female';
              setSex(newSex);
              programSetSex(newSex).catch(console.error);
            }}
            data={[
              { label: 'Male', value: 'male' },
              { label: 'Female', value: 'female' },
            ]}
            fullWidth
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
          />
          <Text size="xs" c="dimmed" mt={4}>
            Used for plate calculator. Default is 20kg in metric mode and 45lb in imperial mode.
          </Text>
        </div>
      </Stack>
    </Drawer>
  )
}
