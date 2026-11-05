import { useEffect, useState } from 'react'
import { Select, Text } from '@mantine/core'
import { fetchStatCategories } from '@/api/client'

interface RankingCategories {
  countries: string[]
  country_regions: Record<string, string[]>
}

const RETRY_MS = 15000
let cached: RankingCategories | null = null

function matchOption(value: string | null | undefined, options: string[]): string | null {
  if (!value) return null
  const wanted = value.trim().toLocaleLowerCase()
  return options.find((option) => option.toLocaleLowerCase() === wanted) ?? null
}

export function useRankingCategories(enabled = true): RankingCategories | null {
  const [categories, setCategories] = useState<RankingCategories | null>(cached)
  useEffect(() => {
    if (!enabled || categories) return
    let cancelled = false
    let timer: number | undefined
    const load = () => {
      fetchStatCategories().then((data: any) => {
        if (cancelled) return
        if (!data || data._status === 503 || data.error) {
          timer = window.setTimeout(load, RETRY_MS)
          return
        }
        cached = { countries: data.countries || [], country_regions: data.country_regions || {} }
        setCategories(cached)
      }).catch(() => {
        if (!cancelled) timer = window.setTimeout(load, RETRY_MS)
      })
    }
    load()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [enabled, categories])
  return categories
}

interface Props {
  country: string | null
  region: string | null
  onChange: (location: { country: string | null; region: string | null }) => void
  disabled?: boolean
  required?: boolean
  enabled?: boolean
}

export function RankingLocationFields({ country, region, onChange, disabled = false, required = false, enabled = true }: Props) {
  const categories = useRankingCategories(enabled)
  const countryValue = categories ? matchOption(country, categories.countries) : null
  const regionOptions = countryValue ? categories?.country_regions[countryValue] ?? [] : []
  const regionValue = matchOption(region, regionOptions)

  useEffect(() => {
    if (!categories) return
    const fixedCountry = matchOption(country, categories.countries)
    const fixedRegion = fixedCountry ? matchOption(region, categories.country_regions[fixedCountry] ?? []) : null
    if ((fixedCountry && fixedCountry !== country) || (fixedRegion && fixedRegion !== region)) {
      onChange({ country: fixedCountry ?? country, region: fixedRegion ?? region })
    }
  }, [categories, country, region, onChange])

  return (
    <>
      <Select
        label="Country"
        placeholder={categories ? 'Select country' : 'Loading countries…'}
        data={categories?.countries ?? []}
        value={countryValue}
        onChange={(value) => onChange({ country: value, region: null })}
        searchable
        clearable={!required}
        required={required}
        disabled={disabled || !categories}
        comboboxProps={{ withinPortal: true, zIndex: 10000 }}
        data-testid="ranking-country"
      />
      <Select
        label="Region / Province / State"
        placeholder={!countryValue ? 'Select country first' : regionOptions.length ? 'Select region' : 'No regions for this country'}
        data={regionOptions}
        value={regionValue}
        onChange={(value) => onChange({ country: countryValue, region: value })}
        searchable
        clearable
        disabled={disabled || !countryValue || regionOptions.length === 0}
        comboboxProps={{ withinPortal: true, zIndex: 10000 }}
        data-testid="ranking-region"
      />
      {!categories && <Text size="xs" c="dimmed">Country and region options load from the rankings dataset; this can take a moment after a restart.</Text>}
    </>
  )
}
