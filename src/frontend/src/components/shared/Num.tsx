import { Text, type TextProps } from '@mantine/core'
import type { ReactNode } from 'react'

interface NumProps extends TextProps {
  children: ReactNode
}

export default function Num({ children, className, ...props }: NumProps) {
  return (
    <Text
      {...props}
      className={['if-num', className].filter(Boolean).join(' ')}
    >
      {children}
    </Text>
  )
}
