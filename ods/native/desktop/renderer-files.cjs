const fs = require('node:fs')
const path = require('node:path')

function resolveRendererFile(root, requestUrl, accept = '') {
  let url, pathname
  try {
    url = new URL(requestUrl)
    pathname = decodeURIComponent(url.pathname)
  } catch {
    return null
  }
  if (url.protocol !== 'ods:' || url.host !== 'app' || url.username || url.password || pathname.includes('\0')) return null
  const candidate = path.resolve(root, `.${pathname}`)
  const relative = path.relative(root, candidate)
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) return null
  if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate
  // BrowserRouter routes load index.html; missing assets remain real 404s.
  if (accept.includes('text/html') && !path.extname(pathname)) return path.join(root, 'index.html')
  return null
}

module.exports = { resolveRendererFile }
