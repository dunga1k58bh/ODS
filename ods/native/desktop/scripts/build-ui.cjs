const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
// Reuse the original ODS UI: ods/extensions/services/dashboard/.
// React components live in its src/ directory; package.json defines the build.
const dashboard = path.resolve(root, '../../extensions/services/dashboard')
if (!process.env.npm_execpath) throw new Error('Run this script through npm run build')
// Equivalent command from the repository root:
// npm --prefix ods/extensions/services/dashboard run build
// The dashboard's "build" script runs "vite build", producing dashboard/dist/.
// Invoke npm through the current Node executable so this also works on Windows
// without spawning a shell or depending on npm.cmd command-line quoting.
const result = spawnSync(process.execPath, [process.env.npm_execpath, '--prefix', dashboard, 'run', 'build'], { stdio: 'inherit' })
if (result.error) throw result.error
if (result.status !== 0) process.exit(result.status || 1)
const renderer = path.join(root, 'dist', 'renderer')
// Copy the built UI into ods/native/desktop/dist/renderer/ for Electron packaging.
// Remove only this generated directory so deleted/renamed assets cannot survive
// a rebuild. Keep the resolved removal target strictly inside the desktop app.
const relativeRenderer = path.relative(root, renderer)
if (!relativeRenderer || relativeRenderer === '..' || relativeRenderer.startsWith(`..${path.sep}`) || path.isAbsolute(relativeRenderer)) {
  throw new Error('Renderer output must stay inside the desktop directory')
}
fs.rmSync(renderer, { recursive: true, force: true })
fs.mkdirSync(renderer, { recursive: true })
fs.cpSync(path.join(dashboard, 'dist'), renderer, { recursive: true })
fs.copyFileSync(path.resolve(root, '../../../LICENSE'), path.join(root, 'dist', 'ODS-LICENSE'))
