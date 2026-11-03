import { useEffect, useRef, useState } from 'react'
import { TextInput, type TextInputProps } from '@mantine/core'

type DraftNumberInputProps = Omit<TextInputProps, 'value' | 'onChange' | 'error' | 'type'> & {
  value: number | null | undefined
  onValueChange: (value: number | null) => void
  isValid?: (value: number) => boolean
  nullable?: boolean
  commitOnlyValid?: boolean
  toDisplay?: (value: number) => number
  fromDisplay?: (value: number) => number
}

function formatValue(value: number | null | undefined, toDisplay?: (value: number) => number): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  const shown = toDisplay ? toDisplay(value) : value
  return String(Math.round(shown * 100) / 100)
}

export default function DraftNumberInput({
  value,
  onValueChange,
  isValid = () => true,
  nullable = true,
  commitOnlyValid = false,
  toDisplay,
  fromDisplay,
  ...inputProps
}: DraftNumberInputProps) {
  const [draft, setDraft] = useState(() => formatValue(value, toDisplay))
  const lastEmitted = useRef<number | null | undefined>(value)
  const lastFormatted = useRef(formatValue(value, toDisplay))

  useEffect(() => {
    const formatted = formatValue(value, toDisplay)
    if (value === lastEmitted.current && formatted === lastFormatted.current) return
    lastEmitted.current = value
    lastFormatted.current = formatted
    setDraft(formatted)
  }, [value, toDisplay])

  const trimmed = draft.trim()
  const parsed = Number(trimmed)
  const invalid = trimmed === ''
    ? !nullable
    : !Number.isFinite(parsed) || !isValid(parsed)

  const emit = (next: number | null) => {
    lastEmitted.current = next
    lastFormatted.current = formatValue(next, toDisplay)
    onValueChange(next)
  }

  const handleChange = (raw: string) => {
    setDraft(raw)
    const text = raw.trim()
    if (text === '') {
      if (nullable) emit(null)
      return
    }
    const number = Number(text)
    if (!Number.isFinite(number)) return
    if (commitOnlyValid && !isValid(number)) return
    emit(fromDisplay ? fromDisplay(number) : number)
  }

  return (
    <TextInput
      {...inputProps}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={draft}
      error={invalid}
      styles={invalid ? { input: { borderColor: 'var(--mantine-color-red-6)' } } : undefined}
      aria-invalid={invalid}
      onChange={(event) => handleChange(event.currentTarget.value)}
    />
  )
}
