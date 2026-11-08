import { useEffect } from 'react'
import { Select } from '@mantine/core'
import rankingLocations from '@/data/ranking-locations.json'

function matchOption(value: string | null | undefined, options: string[]): string | null {
  if (!value) return null
  const wanted = value.trim().toLocaleLowerCase()
  return options.find((option) => option.toLocaleLowerCase() === wanted) ?? null
}

function regionsFor(country: string | null) {
  return country ? rankingLocations.country_regions[country as keyof typeof rankingLocations.country_regions] ?? [] : []
}

interface Props {
  country: string | null
  region: string | null
  onChange: (location: { country: string | null; region: string | null }) => void
  disabled?: boolean
  required?: boolean
}

export function RankingLocationFields({ country, region, onChange, disabled = false, required = false }: Props) {
  const countryValue = matchOption(country, rankingLocations.countries)
  const regionOptions = regionsFor(countryValue)
  const regionValue = matchOption(region, regionOptions)

  useEffect(() => {
    const fixedCountry = matchOption(country, rankingLocations.countries)
    const fixedRegion = matchOption(region, regionsFor(fixedCountry))
    if ((fixedCountry && fixedCountry !== country) || (fixedRegion && fixedRegion !== region)) {
      onChange({ country: fixedCountry ?? country, region: fixedRegion ?? region })
    }
  }, [country, region, onChange])

  return (
    <>
      <Select
        label="Country"
        placeholder="Select country"
        data={rankingLocations.countries}
        value={countryValue}
        onChange={(value) => onChange({ country: value, region: null })}
        searchable
        clearable={!required}
        required={required}
        disabled={disabled}
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
    </>
  )
}
