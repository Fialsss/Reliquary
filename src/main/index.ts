import { app, BrowserWindow, dialog, ipcMain, nativeImage, net, protocol, shell, systemPreferences } from 'electron'
import { readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { Engine } from './engine'

// pic://p/<uid>.webp: the pictures Prepare decoded to disk (the engine's home is userData), straight into <img>
protocol.registerSchemesAsPrivileged([{ scheme: 'pic', privileges: { standard: true, secure: true } }])
const PICTURE = /^[0-9A-F]{16}(\.emblem)?\.webp$/i

let window: BrowserWindow | undefined
let closing = false
let minimizing = false

// The engine outlives the window by a moment when closing: never send to a destroyed one.
const send = (channel: string, value: unknown) => {
  if (window && !window.isDestroyed()) window.webContents.send(channel, value)
}
const engine = new Engine((event) => send('engine:event', event))

/** Fade the real window (not just the page), so closing and minimising feel like the app's own. One fade at a
 * time: restoring from the taskbar fires 'restore' and 'focus' together, and two fades would fight (flicker). */
let stopFade: (() => void) | undefined
function fade(to: number, ms: number): Promise<void> {
  stopFade?.()
  return new Promise((resolve) => {
    const target = window
    if (!target || target.isDestroyed()) return resolve()
    const from = target.getOpacity()
    const start = Date.now()
    const timer = setInterval(() => {
      const k = target.isDestroyed() ? 1 : Math.min(1, (Date.now() - start) / ms)
      if (!target.isDestroyed()) target.setOpacity(from + (to - from) * (1 - (1 - k) ** 3))
      if (k === 1) stopFade?.()
    }, 16)
    stopFade = () => {
      clearInterval(timer)
      stopFade = undefined
      resolve()
    }
  })
}

/** The taskbar icon plays the logo's light: Windows doesn't animate window icons, so the frames of its 5.2 s loop
 * (resources/taskbar, 12 a second) take turns as the window's icon while the app is open. Not with reduced motion. */
function animateIcon(win: BrowserWindow): void {
  if (process.platform !== 'win32' || systemPreferences.getAnimationSettings().prefersReducedMotion) return
  const folder = join(app.getAppPath(), 'resources', 'taskbar')
  const frames = readdirSync(folder).sort().map((name) => nativeImage.createFromPath(join(folder, name)))
  if (!frames.length) return
  let frame = 0
  const timer = setInterval(() => {
    if (win.isDestroyed()) return clearInterval(timer)
    frame = (frame + 1) % frames.length
    win.setIcon(frames[frame])
  }, 5200 / frames.length)
  win.on('closed', () => clearInterval(timer))
}

function createWindow(): void {
  window = new BrowserWindow({
    width: 1160,
    height: 720,
    minWidth: 1040,
    minHeight: 660,
    frame: false,
    show: false,
    backgroundColor: '#0b0b0d',
    title: 'Reliquary',
    icon: join(app.getAppPath(), 'resources', 'icon.png'),
    webPreferences: { preload: join(__dirname, '../preload/index.js') }
  })
  const win = window
  win.once('ready-to-show', () => {
    win.setOpacity(0)
    win.show()
    fade(1, 280)
    animateIcon(win)
  })
  win.on('closed', () => (window = undefined))

  // Alt+F4, the taskbar and our own button all come through here: play the exit first.
  win.on('close', (event) => {
    if (closing) return
    event.preventDefault()
    closing = true
    send('window:state', 'closing')
    fade(0, 200).then(() => win.destroy())
  })
  win.on('maximize', () => send('window:state', 'maximize'))
  win.on('unmaximize', () => send('window:state', 'unmaximize'))
  win.on('restore', () => {
    send('window:state', 'restore')
    fade(1, 240)
  })
  // Safety net: a window that is shown and not on its way out must never stay transparent.
  const reveal = () => {
    if (!closing && !minimizing && !win.isMinimized() && win.getOpacity() < 1) fade(1, 160)
  }
  win.on('focus', reveal)
  win.on('show', reveal)

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })
  // RELIQUARY_PAGE opens a page directly, for screenshots and development
  const page = process.env.RELIQUARY_PAGE ?? ''
  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(`${process.env.ELECTRON_RENDERER_URL}#${page}`)
  else win.loadFile(join(__dirname, '../renderer/index.html'), { hash: page })
}

// Errors cross IPC as data: a rejected handle() prefixes the message with IPC noise.
ipcMain.handle('engine:call', async (_event, method: string, params?: Record<string, unknown>) => {
  try {
    return { result: await engine.call(method, params) }
  } catch (error) {
    return { error: (error as Error).message }
  }
})

ipcMain.handle('dialog:pick', async (_event, kind: 'file' | 'folder', extensions?: string[]) => {
  const { canceled, filePaths } = await dialog.showOpenDialog(window!, {
    properties: [kind === 'folder' ? 'openDirectory' : 'openFile'],
    filters: extensions ? [{ name: extensions.join(', '), extensions }] : undefined
  })
  return canceled ? null : filePaths[0]
})

ipcMain.handle('shell:open', (_event, path: string) => shell.openPath(path))

ipcMain.on('window', async (_event, action: 'minimize' | 'maximize' | 'close') => {
  if (!window) return
  if (action === 'close') window.close()
  else if (action === 'maximize') window.isMaximized() ? window.unmaximize() : window.maximize()
  else {
    // fade out, then minimise invisibly; 'restore' fades back in
    minimizing = true
    send('window:state', 'minimizing')
    await fade(0, 160)
    window?.minimize()
    minimizing = false
  }
})

app.whenReady().then(() => {
  protocol.handle('pic', (request) => {
    const name = new URL(request.url).pathname.slice(1)
    const file = join(app.getPath('userData'), 'pictures2', name)
    // an empty file: Prepare found no picture for that item
    if (!PICTURE.test(name) || !statSync(file, { throwIfNoEntry: false })?.size) return new Response(null, { status: 404 })
    return net.fetch(pathToFileURL(file).toString())
  })
  createWindow()
})
app.on('window-all-closed', () => app.quit())
app.on('before-quit', () => engine.stop())
