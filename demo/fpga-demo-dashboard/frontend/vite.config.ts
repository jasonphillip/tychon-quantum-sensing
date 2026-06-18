import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: Vite serves the UI on 5173 and proxies /api to the FastAPI backend (8077).
// Prod (Phase 5): `vite build` -> dist/, served same-origin by FastAPI (no proxy needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8077', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
