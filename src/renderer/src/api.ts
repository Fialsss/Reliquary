import { useEffect, useRef } from 'react'
import type { ReliquaryApi } from '../../preload'

declare global {
  interface Window {
    reliquary: ReliquaryApi
  }
}

export const api = window.reliquary

export type Check = { ok: boolean; path: string }
export type Status = { game: Check; blender: Check & { version: string }; oodle: Check; depot: Check; home: string }
export type Patch = { patch: string; date: string; manifest: string }
export type Season = { id: string; year: number; season: number; name: string; patches: Patch[]; local: number }
export type DepotFile = { name: string; size: number; category: 'data' | 'textures' | 'meshes' | 'other'; local: boolean }
export type Operator = { uid: string; name: string }
export type Settings = { game_dir: string; blender: string; oodle: string; library: string; steam_user: string }

/** Subscribe to one engine event for the lifetime of the component. */
export function useEngineEvent<T>(name: string, listener: (data: T) => void): void {
  const latest = useRef(listener)
  latest.current = listener
  useEffect(() => api.onEvent((e) => e.event === name && latest.current(e.data as T)), [name])
}

export function bytes(size: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = size
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path
}
