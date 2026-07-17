import { useEffect, useState, useCallback } from 'react'
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
import { defaultBarWeightKgForUnit, useSettingsStore, CURRENCY_OPTIONS, type Theme } from '@/store/settingsStore'
import { useProgramStore } from '@/store/programStore'
import { useAuth } from '@/auth/AuthProvider'
import { fromDisplayUnit, toDisplayUnit } from '@/utils/units'
import { WEEK_START_DAYS, weekStartForBlock } from '@/utils/weekStart'
import { LogIn, LogOut } from 'lucide-react'
import { AGE_CATEGORY_OPTIONS, type Sex, type WeekStartDay } from '@powerlifting/types'
import { getSettings, updateAgeClass, updateRankingLocation } from '@/api/settings'
import { fetchStatCategories } from '@/api/client'
import { GrantsPanel } from '@/components/settings/GrantsPanel'

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
    currency, setCurrency,
  } = useSettingsStore()
  const { program, setSex: programSetSex, setWeekStartDay } = useProgramStore()
  const { user, loading, readOnly, signInDiscord, signInAuthentik, signOut, age_class: authAgeClass } = useAuth()

  const isOpen = drawerOpen && drawerType === 'settings'
  const effectiveSex = program?.meta?.sex ?? sex

  // Ranking location state
  const [rankingCountry, setRankingCountry] = useState<string | null>(null)
  const [rankingRegion, setRankingRegion] = useState<string | null>(null)
  const [rankingCategories, setRankingCategories] = useState<{ countries: string[]; country_regions: Record<string, string[]> } | null>(null)
  const [rankingSaving, setRankingSaving] = useState(false)

  // Age class state (pulled from /api/settings to get full record)
  const [ageClass, setAgeClassState] = useState<string>(authAgeClass || 'open')
  const [ageClassSaving, setAgeClassSaving] = useState(false)

  useEffect(() => {
    setAgeClassState(authAgeClass || 'open')
  }, [authAgeClass])

  // Load current ranking location from settings
  useEffect(() => {
    if (!isOpen || !user) return
    getSettings().then((s) => {
      setRankingCountry(s.ranking_country)
      setRankingRegion(s.ranking_region)
      setAgeClassState(s.age_class || 'open')
    }).catch(() => {})
  }, [isOpen, user])

  // Load categories for dropdowns (reuse existing categories endpoint).
  // Handles 503 (dataset loading) with a retry so the drawer doesn't silently
  // fail to populate the country/region selectors.
  useEffect(() => {
    if (!isOpen || rankingCategories) return
    let cancelled = false
    const load = () => {
      if (cancelled) return
      fetchStatCategories().then((data: any) => {
        if (cancelled) return
        if (!data) return
        if (data._status === 503 || data.error === 'DATASET_NOT_FOUND') {
          setTimeout(load, 30000)
          return
        }
        if (!data.error) {
          setRankingCategories({ countries: data.countries || [], country_regions: data.country_regions || {} })
        }
      }).catch(() => {
        if (!cancelled) setTimeout(load, 30000)
      })
    }
    load()
    return () => { cancelled = true }
  }, [isOpen, rankingCategories])

  const rankingRegionOptions: string[] = rankingCountry
    ? (rankingCategories?.country_regions?.[rankingCountry] ?? [])
    : []

  const handleRankingCountryChange = useCallback((value: string | null) => {
    setRankingCountry(value)
    setRankingRegion(null)
  }, [])

  const saveRankingLocation = useCallback(async () => {
    if (!user) return
    setRankingSaving(true)
    try {
      await updateRankingLocation({ ranking_country: rankingCountry, ranking_region: rankingRegion })
    } catch {
      // silently ignore
    } finally {
      setRankingSaving(false)
    }
  }, [user, rankingCountry, rankingRegion])

  const saveAgeClass = useCallback(async () => {
    if (!user) return
    setAgeClassSaving(true)
    try {
      await updateAgeClass({ age_class: ageClass as 'open' | 'subjunior' | 'junior' | 'master1' | 'master2' | 'master3' | 'master4' })
    } catch {
      // silently ignore
    } finally {
      setAgeClassSaving(false)
    }
  }, [user, ageClass])

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
            <Stack gap="xs">
              <Button
                variant="filled"
                size="sm"
                leftSection={<LogIn size={16} />}
                onClick={signInDiscord}
                fullWidth
                data-testid="settings-signin-discord"
              >
                Sign in with discord
              </Button>
              <Button
                variant="default"
                size="sm"
                leftSection={<LogIn size={16} />}
                onClick={signInAuthentik}
                fullWidth
                data-testid="settings-signin-authentik"
              >
                Sign in with sso
              </Button>
            </Stack>
          )}
        </div>

        <div>
          <SectionLabel>Grants</SectionLabel>
          <GrantsPanel />
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
        {/* Currency */}
        <div>
          <SectionLabel>Currency</SectionLabel>
          <Text size="xs" c="dimmed" mb="sm">
            Used for budget totals and expense entry. Applies everywhere money is shown.
          </Text>
          <Select
            value={currency}
            onChange={(v) => v && setCurrency(v)}
            data={CURRENCY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            searchable
            disabled={readOnly}
            data-testid="settings-currency"
          />
        </div>
        </div>

        {/* Rankings Location */}
        <div>
          <SectionLabel>Rankings Location</SectionLabel>
            <Text size="xs" c="dimmed" mb="sm">
              Used for national and regional percentile cards on the dashboard.
              Options come from the OpenPowerlifting dataset.
            </Text>
            <Stack gap="xs">
              <Select
                label="Country"
                placeholder="Select country"
                data={rankingCategories?.countries ?? []}
                value={rankingCountry}
                onChange={handleRankingCountryChange}
                searchable
                clearable
                disabled={!rankingCategories}
                data-testid="settings-ranking-country"
              />
              <Select
                label="Region / Province / State"
                placeholder={rankingCountry ? 'Select region' : 'Select country first'}
                data={rankingRegionOptions}
                value={rankingRegion}
                onChange={setRankingRegion}
                searchable
                clearable
                disabled={!rankingCountry || rankingRegionOptions.length === 0}
                data-testid="settings-ranking-region"
              />
              <Button
                size="xs"
                variant="light"
                loading={rankingSaving}
                onClick={saveRankingLocation}
                mt={4}
                data-testid="settings-save-ranking-location"
              >
                Save Rankings Location
              </Button>
            </Stack>
          </div>

        {/* Age Class (IPF) */}
        <div>
          <SectionLabel>Age Class</SectionLabel>
          <Text size="xs" c="dimmed" mb="sm">
            IPF age class used for qualifying standards. Defaults to Open.
          </Text>
          <Stack gap="xs">
            <Select
              label="Age class"
              data={AGE_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={ageClass}
              onChange={(v) => v && setAgeClassState(v)}
              disabled={readOnly}
              data-testid="settings-age-class"
            />
            <Button
              size="xs"
              variant="light"
              loading={ageClassSaving}
              onClick={saveAgeClass}
              mt={4}
              disabled={readOnly}
              data-testid="settings-save-age-class"
            >
              Save Age Class
            </Button>
          </Stack>
        </div>
      </Stack>
    </Drawer>
  )
}
