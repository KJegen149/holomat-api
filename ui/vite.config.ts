import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8100', changeOrigin: true },
      '/ws':  { target: 'ws://localhost:8100',  ws: true, changeOrigin: true },
    },
  },
})
