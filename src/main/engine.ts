import { spawn, type ChildProcess } from 'node:child_process'
import { createInterface } from 'node:readline'
import { join } from 'node:path'
import { app } from 'electron'

export type EngineEvent = { event: string; data: unknown }
type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void }

/** The Python engine, spoken to in JSON lines over stdio. Started on first call. */
export class Engine {
  private process?: ChildProcess
  private next = 1
  private pending = new Map<number, Pending>()

  constructor(private readonly onEvent: (event: EngineEvent) => void) {}

  call(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const process = this.process ?? this.start()
    const id = this.next++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      process.stdin!.write(JSON.stringify({ id, method, params }) + '\n')
    })
  }

  stop(): void {
    this.process?.kill()
  }

  private start(): ChildProcess {
    const root = app.isPackaged ? join(process.resourcesPath, 'engine') : join(app.getAppPath(), 'engine')
    const python = process.env.RELIQUARY_PYTHON ?? 'python'
    const child = spawn(python, ['-u', '-X', 'utf8', '-B', '-m', 'reliquary'], {
      cwd: root,
      env: { ...process.env, RELIQUARY_HOME: app.getPath('userData') },
      windowsHide: true
    })
    this.process = child
    createInterface({ input: child.stdout! }).on('line', (line) => this.receive(line))
    child.stderr!.on('data', (chunk) => this.onEvent({ event: 'engine.log', data: String(chunk) }))
    child.on('error', (error) => this.fail(`Could not start Python (${error.message}). Install Python 3.10+ or set RELIQUARY_PYTHON.`))
    child.on('exit', (code) => this.fail(`Engine stopped (exit code ${code})`))
    return child
  }

  private fail(message: string): void {
    for (const { reject } of this.pending.values()) reject(new Error(message))
    this.pending.clear()
    this.process = undefined
    this.onEvent({ event: 'engine.exit', data: message })
  }

  private receive(line: string): void {
    let message: { id?: number; result?: unknown; error?: string; event?: string; data?: unknown }
    try {
      message = JSON.parse(line)
    } catch {
      return
    }
    if (message.event) return this.onEvent({ event: message.event, data: message.data })
    const pending = this.pending.get(message.id!)
    if (!pending) return
    this.pending.delete(message.id!)
    if (message.error !== undefined) pending.reject(new Error(message.error))
    else pending.resolve(message.result)
  }
}
