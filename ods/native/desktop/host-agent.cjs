const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { setTimeout: delay } = require('node:timers/promises')

class HostAgent {
  constructor(config, logPath) {
    const { python, sourceRoot, installDir, port = 7710 } = config
    for (const location of [python, sourceRoot, installDir]) {
      if (typeof location !== 'string' || !path.isAbsolute(location) || !fs.existsSync(location)) {
        throw new Error('Native config requires existing absolute python, sourceRoot and installDir paths')
      }
    }
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid native agent port')
    const script = path.join(sourceRoot, 'bin', 'ods-host-agent.py')
    if (!fs.statSync(python).isFile() || !fs.existsSync(script) || !fs.existsSync(path.join(installDir, '.env'))) {
      throw new Error('Python executable, host-agent source or installation .env is missing')
    }
    this.origin = `http://127.0.0.1:${port}`
    fs.mkdirSync(path.dirname(logPath), { recursive: true })
    const log = fs.openSync(logPath, 'a')
    try {
      this.child = spawn(python, ['-B', script, '--native-windows', '--parent-pipe',
        '--install-dir', installDir, '--port', String(port)], {
        cwd: sourceRoot, windowsHide: true, stdio: ['pipe', log, log],
      })
    } finally {
      fs.closeSync(log)
    }
    this.closed = new Promise(resolve => this.child.once('close', resolve))
    this.child.on('error', error => { this.spawnError = error })
    this.child.stdin.on('error', error => { this.pipeError = error })
  }

  async waitReady(timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (this.spawnError) throw this.spawnError
      if (this.child.exitCode !== null || this.child.signalCode !== null) throw new Error('Native host agent exited before readiness; inspect its log')
      let health
      try {
        const response = await fetch(`${this.origin}/health`, { signal: AbortSignal.timeout(500), redirect: 'error' })
        if (response.ok) health = await response.json()
      } catch (error) {
        // Connection refusal and request timeout are expected during startup.
        if (!(error instanceof TypeError) && error.name !== 'TimeoutError') throw error
      }
      if (health) {
        if (health.mode !== 'native-windows' || health.pid !== this.child.pid) {
          throw new Error('Agent port belongs to a different process; no existing process was adopted')
        }
        return health
      }
      await delay(100)
    }
    throw new Error('Native host agent readiness timed out')
  }

  stop() {
    if (!this.stopping) this.stopping = this.stopOwnedProcess()
    return this.stopping
  }

  async stopOwnedProcess() {
    if (this.child.exitCode !== null || this.child.signalCode !== null || this.spawnError) {
      await this.closed
      return
    }
    this.child.stdin.end()
    let timer
    const stopped = await Promise.race([
      this.closed.then(() => true),
      new Promise(resolve => { timer = setTimeout(() => resolve(false), 15000) }),
    ])
    clearTimeout(timer)
    if (!stopped) {
      this.child.kill()
      await this.closed
      throw new Error('Native host agent exceeded its shutdown grace period and was terminated')
    }
  }
}

module.exports = { HostAgent }
