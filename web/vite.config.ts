import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

const BASE_PATH = process.env.VITE_BASE_PATH || './'

export default defineConfig({
  plugins: [react()],
  base: BASE_PATH,
  build: {
    manifest: true,
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        terms: fileURLToPath(new URL('./terms.html', import.meta.url)),
        privacy: fileURLToPath(new URL('./privacy.html', import.meta.url)),
      },
    },
  },
})
