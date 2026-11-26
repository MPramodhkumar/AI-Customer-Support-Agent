import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api/* is forwarded to the FastAPI backend, so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API || 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') } },
  },
})
