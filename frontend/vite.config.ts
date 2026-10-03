import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs on :8000; proxying keeps the browser on one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  // The live-room chunk is mostly the LiveKit client SDK, loaded only when a deck opens.
  build: { chunkSizeWarningLimit: 700 },
})
