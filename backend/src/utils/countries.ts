import i18nIsoCountries from 'i18n-iso-countries'
import enLocale from 'i18n-iso-countries/langs/en.json'

i18nIsoCountries.registerLocale(enLocale)

const ISO2_PATTERN = /^[A-Za-z]{2}$/

export function resolveCountryIso2(input: string | null | undefined): string | null {
  if (!input) return null
  const trimmed = input.trim()
  if (!trimmed) return null

  if (ISO2_PATTERN.test(trimmed)) {
    return trimmed.toUpperCase()
  }

  const code = i18nIsoCountries.getAlpha2Code(trimmed, 'en')
  return code ?? null
}
