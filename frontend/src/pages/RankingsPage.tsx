import { useState, useEffect, useCallback } from 'react'
import {
  Title,
  Text,
  Paper,
  Grid,
  Select,
  TextInput,
  Button,
  Stack,
  SimpleGrid,
  Group,
  Loader,
  Box,
  Divider,
  Alert
} from '@mantine/core'
import { AlertCircle, Clock } from 'lucide-react'
import { fetchStatCategories, analyzeStats } from '@/api/client'
import { calculateDots } from '@/utils/dots'
import { useSettingsStore } from '@/store/settingsStore'

interface FilterCategories {
  federations: string[]
  countries: string[]
  regions: string[]
  equipment: string[]
  sex: string[]
  age_classes: string[]
  event_types: string[]
  years: number[]
  country_federations?: Record<string, string[]>
  country_regions?: Record<string, string[]>
  region_federations?: Record<string, string[]>
}

interface StatResult {
  n: number
  rank: number
  beat: number
  tied: number
  percentile: number
  pct_of_max: number
  pct_of_mean: number
  median: number
  mean: number
  max: number
}

interface AnalysisResponse {
  dataset_size: number
  computed: { total_kg: number | null; dots: number | null }
  analysis: {
    Squat?: StatResult
    Bench?: StatResult
    Deadlift?: StatResult
    Total?: StatResult
    Dots?: StatResult
  }
}

export default function RankingsPage() {
  const { sex: settingsSex } = useSettingsStore()
  const sexCode = settingsSex === 'female' ? 'F' : 'M'

  const [categories, setCategories] = useState<FilterCategories | null>(null)
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [datasetError, setDatasetError] = useState<string | null>(null)
  const [datasetLoading, setDatasetLoading] = useState(false)

  // Filters
  const [federation, setFederation] = useState<string | null>(null)
  const [country, setCountry] = useState<string | null>(null)
  const [region, setRegion] = useState<string | null>(null)
  const [equipment, setEquipment] = useState<string | null>(null)
  const [sex, setSex] = useState<string | null>(null)
  const [ageClass, setAgeClass] = useState<string | null>(null)
  const [year, setYear] = useState<string | null>(null)
  const [eventType, setEventType] = useState<string | null>(null)
  const [minDots, setMinDots] = useState<number | ''>('')

  // User stats
  const [squat, setSquat] = useState<number | ''>('')
  const [bench, setBench] = useState<number | ''>('')
  const [deadlift, setDeadlift] = useState<number | ''>('')
  const [bodyweight, setBodyweight] = useState<number | ''>('')

  // Derived live preview
  const derivedTotal =
    squat !== '' && bench !== '' && deadlift !== ''
      ? Number(squat) + Number(bench) + Number(deadlift)
      : null
  const derivedDots =
    derivedTotal !== null && bodyweight !== ''
      ? calculateDots(derivedTotal, Number(bodyweight), settingsSex)
      : null

  // Narrowed filter options based on selection
  const federationOptions: string[] = region
    ? (categories?.region_federations?.[region] ?? [])
    : country
      ? (categories?.country_federations?.[country] ?? [])
      : (categories?.federations ?? [])

  const regionOptions: string[] = country
    ? (categories?.country_regions?.[country] ?? [])
    : (categories?.regions ?? [])

  // Clear stale federation/region when narrowed list no longer contains them
  useEffect(() => {
    if (federation && !federationOptions.includes(federation)) {
      setFederation(null)
    }
  }, [federation, federationOptions])

  useEffect(() => {
    if (region && !regionOptions.includes(region)) {
      setRegion(null)
    }
  }, [region, regionOptions])

  const loadCategories = useCallback(() => {
    fetchStatCategories()
      .then(data => {
        setDatasetLoading(false)
        if (data.error === 'DATASET_NOT_FOUND') {
          setDatasetError(data.message)
        } else {
          setCategories(data)
        }
      })
      .catch(err => {
        const status = err?.response?.status
        if (status === 503) {
          setDatasetLoading(true)
          setTimeout(loadCategories, 30000)
        } else {
          console.error('Failed to load categories', err)
        }
      })
  }, [])

  useEffect(() => {
    loadCategories()
  }, [loadCategories])

  const handleAnalyze = async () => {
    setLoading(true)
    try {
      const payload = {
        squat: squat !== '' ? squat : undefined,
        bench: bench !== '' ? bench : undefined,
        deadlift: deadlift !== '' ? deadlift : undefined,
        bodyweight: bodyweight !== '' ? bodyweight : undefined,
        sex_code: sexCode,
        federation: federation || undefined,
        country: country || undefined,
        region: region || undefined,
        equipment: equipment || undefined,
        sex: sex || undefined,
        age_class: ageClass || undefined,
        year: year ? parseInt(year) : undefined,
        event_type: eventType || undefined,
        min_dots: minDots !== '' ? minDots : undefined
      }

      const data = await analyzeStats(payload)
      setAnalysis(data)
    } catch (err) {
      console.error('Failed to analyze stats', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Stack gap="xl" p="md">
      <div>
        <Title order={2}>OpenPowerlifting Rankings</Title>
        <Text c="dimmed">Compare your lifts and DOTS score against the global OpenPowerlifting dataset using dynamic filters.</Text>
      </div>

      {datasetLoading && (
        <Alert variant="light" color="blue" title="Dataset Loading" icon={<Clock size={16} />}>
          <Group gap="sm">
            <Loader size="xs" />
            <Text size="sm">The rankings dataset is loading in the background. This usually takes 1–2 minutes after a server restart. Retrying automatically...</Text>
          </Group>
        </Alert>
      )}

      {datasetError && (
        <Alert variant="light" color="red" title="Dataset Not Found" icon={<AlertCircle size={16} />}>
          {datasetError}
        </Alert>
      )}

      <Grid>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Paper withBorder p="md" radius="md">
            <Title order={4} mb="md">Filters</Title>
            <Stack gap="sm">
              <Select
                label="Sex"
                placeholder="All"
                data={categories?.sex || []}
                value={sex}
                onChange={setSex}
                clearable
              />
              <Select
                label="Equipment"
                placeholder="All"
                data={categories?.equipment || []}
                value={equipment}
                onChange={setEquipment}
                clearable
              />
              <Select
                label="Country"
                placeholder="All"
                data={categories?.countries || []}
                value={country}
                onChange={setCountry}
                searchable
                clearable
              />
              <Select
                label="Region / State"
                placeholder="All"
                data={regionOptions}
                value={region}
                onChange={setRegion}
                searchable
                clearable
              />
              <Select
                label="Federation"
                placeholder="All"
                data={federationOptions}
                value={federation}
                onChange={setFederation}
                searchable
                clearable
              />
              <Select
                label="Age Class"
                placeholder="All"
                data={categories?.age_classes || []}
                value={ageClass}
                onChange={setAgeClass}
                clearable
              />
              <Select
                label="Event Type"
                placeholder="All"
                data={categories?.event_types || []}
                value={eventType}
                onChange={setEventType}
                clearable
              />
              <Select
                label="Year"
                placeholder="All"
                data={categories?.years?.map(String) || []}
                value={year}
                onChange={setYear}
                clearable
              />
            </Stack>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack gap="md">
            <Paper withBorder p="md" radius="md">
              <Title order={4} mb="md">Your Numbers</Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                <TextInput
                  type="number"
                  label="Squat (kg)"
                  placeholder="e.g. 180"
                  value={squat}
                  onChange={(e) => setSquat(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                />
                <TextInput
                  type="number"
                  label="Bench (kg)"
                  placeholder="e.g. 120"
                  value={bench}
                  onChange={(e) => setBench(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                />
                <TextInput
                  type="number"
                  label="Deadlift (kg)"
                  placeholder="e.g. 220"
                  value={deadlift}
                  onChange={(e) => setDeadlift(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                />
                <TextInput
                  type="number"
                  label="Bodyweight (kg)"
                  placeholder="e.g. 83"
                  value={bodyweight}
                  onChange={(e) => setBodyweight(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                />
              </SimpleGrid>

              {(derivedTotal !== null || derivedDots !== null) && (
                <Text size="sm" c="dimmed" mt="sm">
                  {derivedTotal !== null && <>Total: <strong>{derivedTotal} kg</strong></>}
                  {derivedTotal !== null && derivedDots !== null && ' · '}
                  {derivedDots !== null && <>DOTS: <strong>{derivedDots}</strong></>}
                  {' '}(using {settingsSex} coefficients from settings)
                </Text>
              )}

              <Button
                onClick={handleAnalyze}
                loading={loading}
                disabled={!!datasetError || datasetLoading}
                fullWidth
                mt="xl"
              >
                Compare Against Database
              </Button>
            </Paper>

            {analysis && (
              <Paper withBorder p="md" radius="md">
                <Title order={4} mb="xs">
                  Analysis Results ({analysis.dataset_size.toLocaleString()} lifters found)
                </Title>

                {Object.keys(analysis.analysis).length === 0 ? (
                  <Text c="dimmed" mt="md">Please enter at least one lift value to see rankings.</Text>
                ) : (
                  <Stack gap="lg" mt="md">
                    {Object.entries(analysis.analysis).map(([lift, stat]) => (
                      <Box key={lift}>
                        <Text fw={600} size="lg">{lift} Ranking</Text>
                        <SimpleGrid cols={{ base: 2, sm: 4 }} mt="xs">
                          <Paper withBorder p="sm" radius="md" ta="center">
                            <Text c="dimmed" size="sm">Percentile</Text>
                            <Text fw={700} size="xl">{stat.percentile}</Text>
                          </Paper>
                          <Paper withBorder p="sm" radius="md" ta="center">
                            <Text c="dimmed" size="sm">Rank</Text>
                            <Text fw={700} size="xl">#{stat.rank}</Text>
                          </Paper>
                          <Paper withBorder p="sm" radius="md" ta="center">
                            <Text c="dimmed" size="sm">Beat / Tied</Text>
                            <Text fw={700} size="xl">{stat.beat} / {stat.tied}</Text>
                          </Paper>
                          <Paper withBorder p="sm" radius="md" ta="center">
                            <Text c="dimmed" size="sm">% of Max</Text>
                            <Text fw={700} size="xl">{stat.pct_of_max}%</Text>
                          </Paper>
                        </SimpleGrid>
                        <Divider mt="md" />
                      </Box>
                    ))}
                  </Stack>
                )}
              </Paper>
            )}
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
