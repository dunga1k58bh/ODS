import { useEffect, useState } from 'react'

const states = new Set(['starting', 'ready', 'stopping', 'stopped', 'error', 'not-configured'])

export default function NativeHostStatus({ desktop = window.location.protocol === 'ods:' }) {
  const [state, setState] = useState('starting')

  useEffect(() => {
    if (!desktop) return undefined
    let cancelled = false
    let timer
    const controller = new AbortController()
    async function poll() {
      try {
        const response = await fetch('/api/desktop/host-status', { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error('Host status unavailable')
        const status = await response.json()
        if (!cancelled) setState(states.has(status.state) ? status.state : 'error')
      } catch {
        if (!cancelled) setState('error')
      } finally {
        if (!cancelled) timer = setTimeout(poll, 2000)
      }
    }
    poll()
    return () => { cancelled = true; clearTimeout(timer); controller.abort() }
  }, [desktop])

  const error = state === 'error'
    ? 'Local service is unavailable. Check the desktop logs.'
    : state === 'not-configured' ? 'Local service is not configured.' : null
  if (!desktop || !error) return null
  return <div role="alert" className="shrink-0 border-b border-theme-border px-4 py-2 text-xs text-theme-text-muted">{error}</div>
}
