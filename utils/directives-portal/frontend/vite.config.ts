import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const devApiProxy = process.env.VITE_DEV_API_PROXY || 'http://localhost:3006'

export default defineConfig({
  base: '/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    minify: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: devApiProxy,
        changeOrigin: true,
      },
    },
  },
})