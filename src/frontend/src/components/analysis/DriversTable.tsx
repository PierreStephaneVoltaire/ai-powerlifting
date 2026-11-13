import { Fragment, useState } from 'react'
import { Badge, Box, SegmentedControl, Table, Text } from '@mantine/core'
import type { CorrelationFinding } from '@/api/analytics'

type LiftFilter = 'all' | CorrelationFinding['lift']

const EFFECT_COLOR: Record<CorrelationFinding['effect'], string> = {
  helps: 'green',
  hurts: 'red',
  unclear: 'gray',
}

const CONFIDENCE_VARIANT: Record<CorrelationFinding['confidence'], string> = {
  strong: 'filled',
  moderate: 'light',
  weak: 'outline',
}

const TYPE_LABEL: Record<CorrelationFinding['driver_type'], string> = {
  exercise: 'Exercise',
  muscle: 'Muscle',
  sequence: 'Sequence',
}

export function DriversTable({ findings }: { findings: CorrelationFinding[] }) {
  const [lift, setLift] = useState<LiftFilter>('all')
  const [open, setOpen] = useState<number | null>(null)
  const visible = findings
    .map((finding, index) => ({ finding, index }))
    .filter(({ finding }) => lift === 'all' || finding.lift === lift)

  return (
    <>
      <SegmentedControl
        size="xs"
        mb="sm"
        value={lift}
        onChange={(value) => { setLift(value as LiftFilter); setOpen(null) }}
        data={[
          { value: 'all', label: 'All' },
          { value: 'squat', label: 'Squat' },
          { value: 'bench', label: 'Bench' },
          { value: 'deadlift', label: 'Deadlift' },
        ]}
      />
      <Box style={{ overflowX: 'auto' }}>
        <Table fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th ta="left">Lift</Table.Th>
              <Table.Th ta="left">Driver</Table.Th>
              <Table.Th ta="left">Effect</Table.Th>
              <Table.Th ta="left" visibleFrom="sm">Evidence</Table.Th>
              <Table.Th ta="left" visibleFrom="sm">Action</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visible.map(({ finding, index }) => (
              <Fragment key={index}>
                <Table.Tr style={{ verticalAlign: 'top', cursor: 'pointer' }} onClick={() => setOpen(open === index ? null : index)}>
                  <Table.Td style={{ textTransform: 'capitalize' }}>{finding.lift}</Table.Td>
                  <Table.Td>
                    <Text span fw={500} fz="sm" mr={6}>{finding.driver}</Text>
                    <Badge size="xs" variant="default">{TYPE_LABEL[finding.driver_type]}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      size="xs"
                      variant={CONFIDENCE_VARIANT[finding.confidence]}
                      color={EFFECT_COLOR[finding.effect]}
                      title={`${finding.effect} (${finding.confidence} confidence)`}
                      style={{ textTransform: 'capitalize' }}
                    >
                      {finding.effect}
                    </Badge>
                  </Table.Td>
                  <Table.Td fz="xs" visibleFrom="sm">{finding.evidence}</Table.Td>
                  <Table.Td fz="xs" visibleFrom="sm">{finding.action}</Table.Td>
                </Table.Tr>
                {open === index && (
                  <Table.Tr>
                    <Table.Td colSpan={5} fz="xs">
                      <Text fz="xs">Mechanism: {finding.mechanism}</Text>
                      {finding.caveat && <Text fz="xs" c="dimmed">Caveat: {finding.caveat}</Text>}
                      <Box hiddenFrom="sm">
                        {finding.evidence && <Text fz="xs">Evidence: {finding.evidence}</Text>}
                        {finding.action && <Text fz="xs">Action: {finding.action}</Text>}
                      </Box>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Fragment>
            ))}
          </Table.Tbody>
        </Table>
      </Box>
    </>
  )
}
