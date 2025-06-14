import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
    plugins: [react()],
    server: {
      host: true,
      port: 3000,
      watch: {
        usePolling: true
      },
      hmr: {
        protocol: 'wss',
        host: new URL(env.VITE_FRONTEND_URL).hostname,
        clientPort: 443
      }
    }
  }
}) 