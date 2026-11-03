import React from 'react'
import { Badge, Tooltip } from '@mantine/core'
import { LoadSource } from '@powerlifting/types'

interface Props {
  source?: LoadSource | string
  type?: LoadSource | string
  size?: 'xs' | 'sm' | 'md'
}

export const LoadTypeBadge: React.FC<Props> = ({ source, type, size = 'xs' }) => {
  const s = source || type
  switch (s) {
    case 'rpe':
      return (
        <Tooltip label="RPE-based target">
          <Badge color="blue" variant="filled" size={size} radius="sm">RPE</Badge>
        </Tooltip>
      )
    case 'percentage':
      return (
        <Tooltip label="Percentage of max">
          <Badge color="green" variant="filled" size={size} radius="sm">%</Badge>
        </Tooltip>
      )
    case 'absolute':
      return null // Default, no badge needed usually but let's see
    case 'unresolvable':
      return (
        <Tooltip label="Unresolvable - manual entry needed">
          <Badge color="red" variant="filled" size={size} radius="sm">?</Badge>
        </Tooltip>
      )
    default:
      return null
  }
}
