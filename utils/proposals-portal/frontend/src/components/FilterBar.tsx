import { useState } from 'react'
import { Box, Button, Group, Select, TextInput, Stack } from '@mantine/core'
import { Search, X } from 'lucide-react'
import { TYPE_LABELS, type ProposalAuthor, type ProposalFilters, type ProposalType } from '../types'

interface FilterBarProps {
  filters: ProposalFilters
  onFilterChange: (filters: ProposalFilters) => void
}

export function FilterBar({ filters, onFilterChange }: FilterBarProps) {
  const [searchQuery, setSearchQuery] = useState(filters.q ?? '')

  const handleFilterChange = (key: keyof ProposalFilters, value: string | null) => {
    const newFilters: ProposalFilters = { ...filters }
    if (!value) {
      delete newFilters[key]
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(newFilters as any)[key] = value
    }
    onFilterChange(newFilters)
  }

  const handleSearch = () => {
    handleFilterChange('q', searchQuery || null)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch()
  }

  const clearFilters = () => {
    setSearchQuery('')
    onFilterChange({})
  }

  const hasActiveFilters = Object.keys(filters).length > 0

  const typeOptions = [
    { value: '', label: 'All Types' },
    ...Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label })),
  ]

  const authorOptions = [
    { value: '', label: 'All Authors' },
    { value: 'agent', label: '🤖 Agent' },
    { value: 'user', label: '👤 You' },
  ]

  return (
    <Box
      className="if-mock-card"
      mb="md"
      style={{ padding: '12px 14px' }}
    >
      <Stack gap="sm">
        <Group gap="sm" wrap="wrap" align="flex-end">
          <TextInput
            label="Search"
            placeholder="Search title or rationale..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.currentTarget.value)}
            onKeyDown={handleKeyDown}
            leftSection={<Search size={14} />}
            style={{ flex: 1, minWidth: 220 }}
            size="sm"
          />
          <Select
            label="Type"
            data={typeOptions}
            value={filters.type ?? ''}
            onChange={(value) => handleFilterChange('type', value as ProposalType | null)}
            size="sm"
            style={{ minWidth: 160 }}
            allowDeselect={false}
          />
          <Select
            label="Author"
            data={authorOptions}
            value={filters.author ?? ''}
            onChange={(value) => handleFilterChange('author', value as ProposalAuthor | null)}
            size="sm"
            style={{ minWidth: 140 }}
            allowDeselect={false}
          />
          {hasActiveFilters && (
            <Button
              variant="subtle"
              color="gray"
              size="sm"
              leftSection={<X size={12} />}
              onClick={clearFilters}
            >
              Clear
            </Button>
          )}
        </Group>
      </Stack>
    </Box>
  )
}
