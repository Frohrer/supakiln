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
      hmr: mode === 'development' ? {
        protocol: 'wss',
        host: new URL(env.VITE_FRONTEND_URL || 'https://localhost:3000').hostname,
        clientPort: 443
      } : false  // Disable HMR in production
    },
    build: {
      // Optimize for production
      minify: 'terser',
      sourcemap: false,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            ui: ['@mui/material', '@mui/icons-material']
          }
        }
      }
    }
  }
}) 