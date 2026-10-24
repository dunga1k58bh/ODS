import { act, render, screen } from '@testing-library/react'
import NativeHostStatus from './NativeHostStatus'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('does not render or poll in the web dashboard', () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  const { container } = render(<NativeHostStatus desktop={false} />)
  expect(container).toBeEmptyDOMElement()
  expect(fetch).not.toHaveBeenCalled()
})

it('checks in the background, shows only failures and clears the alert after recovery', async () => {
  vi.useFakeTimers()
  let finishStartup
  const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finishStartup = resolve }))
  vi.stubGlobal('fetch', fetch)
  const view = render(<NativeHostStatus desktop />)
  expect(view.container).toBeEmptyDOMElement()
  await act(async () => finishStartup({ ok: true, json: async () => ({ state: 'ready' }) }))
  expect(view.container).toBeEmptyDOMElement()
  fetch.mockRejectedValueOnce(new TypeError('unavailable'))
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(screen.getByRole('alert')).toHaveTextContent('unavailable')
  fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ state: 'ready' }) })
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(view.container).toBeEmptyDOMElement()
  view.unmount()
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(fetch).toHaveBeenCalledTimes(3)
})

it.each(['starting', 'ready', 'stopping', 'stopped'])('keeps the original UI unchanged for %s', async state => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state }) }))
  let view
  await act(async () => { view = render(<NativeHostStatus desktop />) })
  expect(view.container).toBeEmptyDOMElement()
})

it('reports missing native configuration as an error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: 'not-configured' }) }))
  await act(async () => { render(<NativeHostStatus desktop />) })
  expect(screen.getByRole('alert')).toHaveTextContent('not configured')
})
