import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '127.0.0.1', // Localhost only - not exposed to network
    port: 5173,
    strictPort: true, // Fail if port is in use (needed for Tauri)
  },
  // Clear screen disabled for Tauri (avoids console artifacts)
  clearScreen: false,
  // Env prefix for Tauri
  envPrefix: ['VITE_', 'TAURI_'],
})
