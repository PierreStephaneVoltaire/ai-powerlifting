import { Drawer, SegmentedControl, NumberInput, Text, Stack, Group, Button, Select } from '@mantine/core'
import { useUiStore } from '@/store/uiStore'
import { defaultBarWeightKgForUnit, useSettingsStore, type Theme } from '@/store/settingsStore'
import { useProgramStore } from '@/store/programStore'
import { fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { WEEK_START_DAYS, weekStartForBlock } from '@/utils/weekStart'
import { Sun, Moon, Monitor } from 'lucide-react'
import type { WeekStartDay } from '@powerlifting/types'

const themeOptions: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

export default function SettingsDrawer() {
  const { drawerOpen, drawerType, closeDrawer } = useUiStore()
  const { unit, theme, setTheme, sex, setSex, barWeightKg, setBarWeight } = useSettingsStore()
  const { program, setSex: programSetSex, setWeekStartDay } = useProgramStore()

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
          <NumberInput
            value={toDisplayUnit(barWeightKg, unit)}
            onChange={(val) => setBarWeight(
              typeof val === 'number'
                ? fromDisplayUnit(val, unit)
                : defaultBarWeightKgForUnit(unit),
            )}
            min={0}
            max={unit === 'kg' ? 50 : 120}
            step={unit === 'kg' ? 0.25 : 0.5}
            decimalScale={2}
            hideControls
          />
          <Text size="xs" c="dimmed" mt={4}>
            Used for plate calculator. Default is 20kg in metric mode and 45lb in imperial mode.
          </Text>
        </div>
      </Stack>
    </Drawer>
  )
}
