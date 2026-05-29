import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MantineProvider, createTheme, type CSSVariablesResolver } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import App from './App'
import './index.css'

const theme = createTheme({
  primaryColor: 'violet',
  defaultRadius: 'sm',
  fontFamily: "'DM Sans', sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', monospace",
  headings: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontWeight: '600',
  },
})

const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--mantine-color-violet-6': '#7c3aed',
  },
  light: {
    '--bg-base': '#f6f8fb',
    '--bg-surface': '#ffffff',
    '--bg-elevated': '#f1f5f9',
    '--text-primary': '#111827',
    '--text-secondary': '#526071',
    '--text-muted': '#94a3b8',
  },
  dark: {
    '--bg-base': '#090b10',
    '--bg-surface': '#111318',
    '--bg-elevated': '#181b24',
    '--text-primary': '#e2e6f0',
    '--text-secondary': '#8891aa',
    '--text-muted': '#4a5068',
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      cssVariablesResolver={cssVariablesResolver}
    >
      <Notifications position="top-right" />
      <BrowserRouter basename="/">
        <App />
      </BrowserRouter>
    </MantineProvider>
  </React.StrictMode>
)