import { useCallback, useEffect, useState } from 'react'
import { Button, SegmentedControl, Select, Stack, Text, TextInput, Title } from '@mantine/core'
import { defaultBarWeightKgForUnit, useSettingsStore, type Theme } from '@/store/settingsStore'
import { useProgramStore } from '@/store/programStore'
import { useAuth } from '@/auth/AuthProvider'
import { fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { WEEK_START_DAYS, weekStartForBlock } from '@/utils/weekStart'
import { AGE_CATEGORY_OPTIONS, type Sex, type WeekStartDay } from '@powerlifting/types'
import { getSettings, updateAgeClass, updateRankingLocation, type UserSettings } from '@/api/settings'
import { RankingLocationFields } from '@/components/settings/RankingLocationFields'

const themeOptions: { value: Theme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
]

function SectionTitle({ children }: { children: string }) {
  return <Title order={4}>{children}</Title>
}

export default function PreferencesSettings() {
  const {
    unit,
    theme,
    setTheme,
    sex,
    setSex,
    barWeightKg,
    setBarWeight,
    defaultSessionsView,
    setDefaultSessionsView,
  } = useSettingsStore()
  const { program, setSex: programSetSex, setWeekStartDay } = useProgramStore()
  const { user, readOnly, age_class: authAgeClass } = useAuth('settings')
  const effectiveSex = program?.meta?.sex ?? sex

  const [rankingCountry, setRankingCountry] = useState<string | null>(null)
  const [rankingRegion, setRankingRegion] = useState<string | null>(null)
  const [rankingSaving, setRankingSaving] = useState(false)
  const [ageClass, setAgeClass] = useState<string>(authAgeClass || 'open')
  const [ageClassSaving, setAgeClassSaving] = useState(false)

  useEffect(() => {
    setAgeClass(authAgeClass || 'open')
  }, [authAgeClass])

  useEffect(() => {
    if (!user) return
    let current = true
    getSettings().then((settings) => {
      if (!current) return
      setRankingCountry(settings.ranking_country)
      setRankingRegion(settings.ranking_region)
      setAgeClass(settings.age_class || 'open')
    }).catch(() => {})
    return () => { current = false }
  }, [user])

  useEffect(() => {
    const programSex = program?.meta?.sex
    if (programSex && programSex !== sex) setSex(programSex)
  }, [program?.meta?.sex, setSex, sex])

  const saveRankingLocation = useCallback(async () => {
    if (!user) return
    setRankingSaving(true)
    try {
      await updateRankingLocation({ ranking_country: rankingCountry, ranking_region: rankingRegion })
    } catch {
      return
    } finally {
      setRankingSaving(false)
    }
  }, [user, rankingCountry, rankingRegion])

  const saveAgeClass = useCallback(async () => {
    if (!user) return
    setAgeClassSaving(true)
    try {
      await updateAgeClass({ age_class: ageClass as UserSettings['age_class'] })
    } catch {
      return
    } finally {
      setAgeClassSaving(false)
    }
  }, [user, ageClass])

  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <SectionTitle>Appearance</SectionTitle>
        <SegmentedControl
          value={theme}
          onChange={(value) => setTheme(value as Theme)}
          data={themeOptions}
          fullWidth
          className="if-segmented"
        />
      </Stack>

      <Stack gap="md">
        <SectionTitle>Training preferences</SectionTitle>
        <Select
          label="Default Sessions View"
          value={defaultSessionsView}
          onChange={(value) => value && setDefaultSessionsView(value as 'Month' | 'Agenda' | 'Compact')}
          data={[
            { label: 'Agenda', value: 'Agenda' },
            { label: 'Month', value: 'Month' },
            { label: 'Compact', value: 'Compact' },
          ]}
          data-testid="settings-default-sessions-view"
        />
        <div>
          <Text size="sm" fw={500} mb="xs">Sex (for DOTS calculation)</Text>
          <SegmentedControl
            value={effectiveSex}
            onChange={(value) => {
              const next = value as Sex
              setSex(next)
              if (program) programSetSex(next).catch(console.error)
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
        <Select
          label="Training Week Start"
          value={weekStartForBlock(program, 'current')}
          onChange={(value) => value && setWeekStartDay(value as WeekStartDay).catch(console.error)}
          data={WEEK_START_DAYS.map((day) => ({ value: day, label: day }))}
          disabled={readOnly}
          data-testid="settings-week-start"
        />
        <TextInput
          label={`Bar Weight (${unit})`}
          description="Used for plate calculator. Default is 20kg in metric mode and 45lb in imperial mode."
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
      </Stack>

      <Stack gap="xs">
        <SectionTitle>Rankings Location</SectionTitle>
        <Text size="xs" c="dimmed">
          Used for national and regional percentile cards on the dashboard.
          Options come from the app's country and region reference data.
        </Text>
        <RankingLocationFields
          country={rankingCountry}
          region={rankingRegion}
          onChange={({ country, region }) => { setRankingCountry(country); setRankingRegion(region) }}
        />
        <Button
          size="xs"
          variant="light"
          loading={rankingSaving}
          onClick={saveRankingLocation}
          data-testid="settings-save-ranking-location"
        >
          Save Rankings Location
        </Button>
      </Stack>

      <Stack gap="xs">
        <SectionTitle>Age Class</SectionTitle>
        <Text size="xs" c="dimmed">IPF age class used for qualifying standards. Defaults to Open.</Text>
        <Select
          label="Age class"
          data={AGE_CATEGORY_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
          value={ageClass}
          onChange={(value) => value && setAgeClass(value)}
          disabled={readOnly}
          data-testid="settings-age-class"
        />
        <Button
          size="xs"
          variant="light"
          loading={ageClassSaving}
          onClick={saveAgeClass}
          disabled={readOnly}
          data-testid="settings-save-age-class"
        >
          Save Age Class
        </Button>
      </Stack>
    </Stack>
  )
}
