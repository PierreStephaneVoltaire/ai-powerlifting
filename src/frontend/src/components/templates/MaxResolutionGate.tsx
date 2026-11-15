import React, { useState } from 'react'
import { Modal, Stack, TextInput, Button, Group, Table, Alert } from '@mantine/core'
import { Info } from 'lucide-react'
import { estimateExercises, fetchGlossary } from '../../api/client'

interface Props {
  missingMaxes: string[]
  onResolved: (values: Record<string, number>) => void
  onCancel: () => void
}

export const MaxResolutionGate: React.FC<Props> = ({ missingMaxes, onResolved, onCancel }) => {
  const [values, setValues] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})

  const handleManualChange = (exercise: string, val: number | string) => {
    setValues(prev => ({ ...prev, [exercise]: typeof val === 'number' ? val : 0 }))
  }

  const handleEstimate = async (exercise: string) => {
    setLoading(prev => ({ ...prev, [exercise]: true }))
    try {
      const result = await estimateExercises([exercise], ['e1rm'])
      if (result.saved.length === 0) return
      const estimated = (await fetchGlossary()).find((entry) => entry.id === exercise)?.e1rm_estimate?.value_kg
      if (estimated) {
        setValues(prev => ({ ...prev, [exercise]: estimated }))
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(prev => ({ ...prev, [exercise]: false }))
    }
  }

  const isComplete = missingMaxes.every(m => !!values[m])

  return (
    <Modal opened={true} onClose={onCancel} title="Missing Exercise Maxes" size="lg">
      <Stack gap="md">
        <Alert icon={<Info size={16} />} color="blue">
          The following exercises are used in the template but don't have a recorded max. 
          Please provide an estimate for percentage-based calculations.
        </Alert>

        <Table verticalSpacing="sm">
          <thead>
            <tr>
              <th>Exercise</th>
              <th>Estimate (kg)</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {missingMaxes.map(m => (
              <tr key={m}>
                <td>{m}</td>
                <td>
                  <TextInput 
                    type="number"
                    value={values[m] ?? ''}
                    onChange={(e) => handleManualChange(m, Number(e.currentTarget.value) || 0)}
                    placeholder="e.g. 140"
                    step={2.5}
                  />
                </td>
                <td>
                  <Button 
                    variant="light" 
                    size="xs" 
                    onClick={() => handleEstimate(m)}
                    loading={loading[m]}
                  >
                    AI Estimate
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>

        <Group justify="flex-end" mt="xl">
          <Button variant="subtle" onClick={onCancel}>Cancel</Button>
          <Button disabled={!isComplete} onClick={() => onResolved(values)}>
            Confirm & Apply
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
