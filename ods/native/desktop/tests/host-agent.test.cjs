const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { test } = require('node:test')
const { HostAgent } = require('../host-agent.cjs')

const python = process.env.ODS_TEST_PYTHON || path.resolve(__dirname, '../../windows/build/python-3.13.17/python.exe')
const supported = process.platform === 'win32' && fs.existsSync(python)

test('owns a real native agent, waits for its PID and shuts it down through EOF', { skip: !supported }, async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ods-agent-'))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  fs.writeFileSync(path.join(directory, '.env'), 'ODS_AGENT_KEY=test-desktop-key\n')
  const server = http.createServer((_request, response) => {
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ mode: 'native-windows', pid: -1 }))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  const config = { python, sourceRoot: path.resolve(__dirname, '../../..'), installDir: directory, port }
  const agent = new HostAgent(config, path.join(directory, 'agent.log'))
  assert.deepEqual(agent.getStatus(), { state: 'starting' })
  try {
    const health = await agent.waitReady()
    assert.equal(health.pid, agent.child.pid)
    assert.equal(health.mode, 'native-windows')
    assert.deepEqual(agent.getStatus(), { state: 'ready' })
  } finally {
    await agent.stop()
  }
  assert.equal(agent.child.exitCode, 0)
  assert.deepEqual(agent.getStatus(), { state: 'stopped' })
  await agent.stop()

  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve))
  const rejected = new HostAgent(config, path.join(directory, 'agent.log'))
  try {
    await assert.rejects(rejected.waitReady(), /different process|exited before readiness/)
    assert.equal(server.listening, true)
  } finally {
    await rejected.stop()
    await new Promise(resolve => server.close(resolve))
  }
  const crashed = new HostAgent(config, path.join(directory, 'agent.log'))
  try {
    await crashed.waitReady()
    crashed.child.kill()
    await crashed.closed
    assert.deepEqual(crashed.getStatus(), { state: 'error' })
  } finally {
    await crashed.stop()
  }
})
