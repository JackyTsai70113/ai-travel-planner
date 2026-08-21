import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BASE_PATH = process.env.VITE_BASE_PATH || './'

export default defineConfig({
  plugins: [react()],
  base: BASE_PATH,
  build: {
    manifest: true,
  },
})
