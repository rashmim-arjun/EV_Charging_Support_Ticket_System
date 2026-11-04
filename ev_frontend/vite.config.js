import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = process.env.EV_API_TARGET || env.EV_API_TARGET || 'http://127.0.0.1:8000'
  const proxy = { '/api': {
    target,
    changeOrigin: true,
    configure(server) {
      server.on('error', (error, req, res) => {
        if (!res.writeHead || res.headersSent || res.writableEnded) return
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: {
          code: 'backend_unavailable',
          message: `Cannot connect to the FastAPI backend at ${target}. Start the backend on that address, then retry.`,
          details: { reason: error.code || 'connection_failed' },
        } }))
      })
    },
  } }
  return {
    plugins: [react()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 5173, strictPort: true, proxy },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.js',
      include: ['src/**/*.test.{js,jsx}'],
      globals: true,
    },
    build: {
      rollupOptions: { output: { manualChunks: { vendor: ['react', 'react-dom', 'react-router-dom'], charts: ['recharts'] } } },
    },
  }
})
