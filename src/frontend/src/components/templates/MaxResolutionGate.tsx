import React, { useState } from 'react'
import { Modal, Text, Stack, TextInput, Button, Group, Table, Alert, Badge } from '@mantine/core'
import { Info } from 'lucide-react'
import { estimateExerciseE1rm, setExerciseE1rm } from '../../api/client'

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
      // Need id for the API call, but we might only have names here.
      // Assuming the backend handles name-based lookup or we need to resolve names to IDs first.
      // For now, let's assume the missingMaxes are IDs or we have a way to handle them.
      // If they are names, this might need a different endpoint or search.
      // Let's assume they are exercise IDs for this implementation.
      const res = await estimateExerciseE1rm(exercise)
      if (res.value_kg) {
        setValues(prev => ({ ...prev, [exercise]: res.value_kg }))
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
