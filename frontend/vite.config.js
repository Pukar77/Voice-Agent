import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend. Everything below is proxied so the browser only ever
// talks to the Vite dev server (no CORS, one origin, mic access stays happy).
const backend = process.env.VITE_BACKEND || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/ask': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
      '/ws': { target: backend, ws: true, changeOrigin: true },
    },
  },
})
