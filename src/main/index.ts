import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { join } from 'node:path'
import { Engine } from './engine'

let window: BrowserWindow | undefined
const engine = new Engine((event) => window?.webContents.send('engine:event', event))

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
  window.once('ready-to-show', () => window?.show())
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })
  // RELIQUARY_PAGE opens a page directly, for screenshots and development
  const page = process.env.RELIQUARY_PAGE ?? ''
  if (process.env.ELECTRON_RENDERER_URL) window.loadURL(`${process.env.ELECTRON_RENDERER_URL}#${page}`)
  else window.loadFile(join(__dirname, '../renderer/index.html'), { hash: page })
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

ipcMain.on('window', (_event, action: 'minimize' | 'maximize' | 'close') => {
  if (!window) return
  if (action === 'minimize') window.minimize()
  else if (action === 'maximize') window.isMaximized() ? window.unmaximize() : window.maximize()
  else window.close()
})

app.whenReady().then(createWindow)
app.on('window-all-closed', () => {
  engine.stop()
  app.quit()
})
