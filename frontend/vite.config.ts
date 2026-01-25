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
    host: '0.0.0.0', // Exposed to network (needed for WSL2 -> Windows access)
    port: 5173,
    strictPort: true, // Fail if port is in use (needed for Tauri)
  },
  // Clear screen disabled for Tauri (avoids console artifacts)
  clearScreen: false,
  // Env prefix for Tauri
  envPrefix: ['VITE_', 'TAURI_'],
})
