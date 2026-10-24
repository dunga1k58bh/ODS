const { app, BrowserWindow, dialog, net, protocol, session } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { resolveRendererFile } = require('./renderer-files.cjs')

protocol.registerSchemesAsPrivileged([
  { scheme: 'ods', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
])

const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'none'"
let window

function createWindow() {
  window = new BrowserWindow({
    title: 'ODS', width: 1280, height: 850, minWidth: 800, minHeight: 600,
    backgroundColor: '#111212', show: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  })
  window.removeMenu()
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', (event, url) => {
    const target = new URL(url)
    if (target.protocol !== 'ods:' || target.host !== 'app') event.preventDefault()
  })
  window.once('ready-to-show', () => window.show())
  window.on('closed', () => { window = null })
  return window.loadURL('ods://app/')
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (window) {
      if (window.isMinimized()) window.restore()
      window.focus()
    }
  })
  app.whenReady().then(async () => {
    const root = path.join(app.getAppPath(), 'dist', 'renderer')
    if (!fs.existsSync(path.join(root, 'index.html'))) throw new Error('Dashboard build missing. Run npm run build first.')
    session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
    session.defaultSession.setPermissionCheckHandler(() => false)
    // Until backend wiring exists, the shell serves only its bundled UI.
    session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
      const bundledFile = details.url.startsWith(pathToFileURL(root + path.sep).href)
      callback({ cancel: !/^(ods:|data:|blob:)/.test(details.url) && !bundledFile })
    })
    protocol.handle('ods', async request => {
      const url = new URL(request.url)
      if (url.host !== 'app' || url.username || url.password) return new Response(null, { status: 403 })
      if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
        return new Response(JSON.stringify({ detail: 'Native desktop backend is not connected yet' }), {
          status: 503, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
        })
      }
      if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, { status: 405 })
      const file = resolveRendererFile(root, request.url, request.headers.get('accept') || '')
      if (!file) return new Response(null, { status: 404 })
      const response = await net.fetch(pathToFileURL(file).href)
      const headers = new Headers(response.headers)
      headers.set('Content-Security-Policy', csp)
      return new Response(request.method === 'HEAD' ? null : response.body, {
        status: response.status, headers,
      })
    })
    await createWindow()
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow().catch(error => dialog.showErrorBox('ODS', error.message))
    })
  }).catch(error => {
    dialog.showErrorBox('ODS startup failed', error.message)
    app.quit()
  })
  app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
}
