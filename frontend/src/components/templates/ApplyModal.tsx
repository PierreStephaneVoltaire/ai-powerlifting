import React, { useEffect, useState } from 'react'
import { Modal, Select, Button, Stack, Group } from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { applyTemplate } from '../../api/client'
import { useProgramStore } from '../../store/programStore'
import { WEEK_START_DAYS, weekStartForBlock } from '../../utils/weekStart'
import type { WeekStartDay } from '@powerlifting/types'

interface Props {
  opened: boolean
  onClose: () => void
  sk: string
  onApply: (data: any) => void
}

export const ApplyModal: React.FC<Props> = ({ opened, onClose, sk, onApply }) => {
  const [target, setTarget] = useState<string>('new_block')
  const [startDate, setStartDate] = useState<string | null>(new Date().toISOString().split('T')[0])
  const [weekStartDay, setWeekStartDay] = useState<WeekStartDay>('Monday')
  const [loading, setLoading] = useState(false)
  const { program } = useProgramStore()

  useEffect(() => {
    if (opened) setWeekStartDay(weekStartForBlock(program, 'current'))
  }, [opened, program])

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const res = await applyTemplate(sk, {
        target,
        start_date: startDate || undefined,
        week_start_day: weekStartDay,
      })
      onApply(res)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Apply Template" size="md">
      <Stack gap="md">
        <Select 
          label="Apply Strategy" 
          value={target}
          onChange={(v) => setTarget(v || 'new_block')}
          data={[
            { value: 'new_block', label: 'Create new training block' },
            { value: 'append', label: 'Append to current block' },
            { value: 'replace_incomplete', label: 'Replace non-completed sessions' },
          ]}
        />

        <DatePickerInput 
          label="Start Date" 
          placeholder="Pick date" 
          value={startDate} 
          onChange={setStartDate} 
        />

        <Select
          label="Week Start Day" 
          value={weekStartDay} 
          onChange={(value) => value && setWeekStartDay(value as WeekStartDay)}
          data={WEEK_START_DAYS.map((day) => ({ value: day, label: day }))}
        />

        <Group justify="flex-end" mt="xl">
          <Button variant="subtle" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} loading={loading}>Apply</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
