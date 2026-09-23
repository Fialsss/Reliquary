import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

type EngineEvent = { event: string; data: unknown }

const api = {
  async call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T> {
    const reply = await ipcRenderer.invoke('engine:call', method, params)
    if ('error' in reply) throw new Error(reply.error)
    return reply.result as T
  },
  onEvent(listener: (event: EngineEvent) => void): () => void {
    const handler = (_: IpcRendererEvent, event: EngineEvent) => listener(event)
    ipcRenderer.on('engine:event', handler)
    return () => ipcRenderer.removeListener('engine:event', handler)
  },
  pick: (kind: 'file' | 'folder', extensions?: string[]): Promise<string | null> =>
    ipcRenderer.invoke('dialog:pick', kind, extensions),
  open: (path: string): Promise<string> => ipcRenderer.invoke('shell:open', path),
  window: (action: 'minimize' | 'maximize' | 'close') => ipcRenderer.send('window', action),
  onWindow(listener: (state: 'closing' | 'minimizing' | 'maximize' | 'unmaximize' | 'restore') => void): () => void {
    const handler = (_: IpcRendererEvent, state: Parameters<typeof listener>[0]) => listener(state)
    ipcRenderer.on('window:state', handler)
    return () => ipcRenderer.removeListener('window:state', handler)
  }
}

contextBridge.exposeInMainWorld('reliquary', api)

export type ReliquaryApi = typeof api
