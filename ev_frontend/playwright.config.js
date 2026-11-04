import { defineConfig } from '@playwright/test'

const environment = process.env.E2E_CLEAN ? '.venv-clean' : '.venv'
const isolated = process.env.E2E_ISOLATED === '1'
const apiPort = isolated ? 8010 : 8000
const uiPort = isolated ? 5174 : 5173
const productionCommand = `npm run preview -- --host localhost --port ${uiPort} --strictPort${isolated ? ' --outDir .tmp/communication-preview' : ''}`
const pythonCommand = process.platform === 'win32'
  ? `..\\${environment}\\Scripts\\python.exe ..\\ev_backend\\scripts\\smoke_server.py --port ${apiPort} --ui-port ${uiPort}`
  : `../${environment}/bin/python ../ev_backend/scripts/smoke_server.py --port ${apiPort} --ui-port ${uiPort}`

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  reporter: [['list']],
  outputDir: 'test-results',
  use: { baseURL: `http://localhost:${uiPort}`, channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : 'chromium'), actionTimeout: 10000, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    { command: pythonCommand, url: `http://127.0.0.1:${apiPort}/api/v1/health`, reuseExistingServer: false, timeout: 30000 },
    { command: process.env.E2E_PRODUCTION ? productionCommand : `npm run dev -- --host localhost --port ${uiPort} --strictPort`, url: `http://localhost:${uiPort}`, env: { VITE_API_BASE: '/api/v1', EV_API_TARGET: `http://127.0.0.1:${apiPort}` }, reuseExistingServer: false, timeout: 30000 },
  ],
})
