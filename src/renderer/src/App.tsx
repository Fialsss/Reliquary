import { useCallback, useEffect, useState } from 'react'
import { Archive, Crosshair, House, Minus, SlidersHorizontal, Square, Users, X } from 'lucide-react'
import { api, useEngineEvent, type Status } from './api'
import { Mark, Shards } from './art'
import { useI18n } from './i18n'
import Home from './pages/Home'
import Vault from './pages/Vault'
import Operators from './pages/Operators'
import Armory from './pages/Armory'
import Settings from './pages/Settings'

export type Page = 'home' | 'operators' | 'armory' | 'vault' | 'settings'
export type Art = { seed: number; hue: number }

const NAV = [
  ['home', House],
  ['operators', Users],
  ['armory', Crosshair],
  ['vault', Archive],
  ['settings', SlidersHorizontal]
] as const

export default function App() {
  const { t } = useI18n()
  const [page, setPage] = useState<Page>(() => {
    const hash = location.hash.slice(1)
    return NAV.some(([id]) => id === hash) ? (hash as Page) : 'home'
  })
  const [art, setArt] = useState<Art>({ seed: 41, hue: 196 })
  const [engine, setEngine] = useState<'starting' | 'ready' | 'offline'>('starting')
  const [status, setStatus] = useState<Status | null>(null)

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.call<Status>('env.status'))
      setEngine('ready')
    } catch {
      setEngine('offline')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])
  useEngineEvent('engine.exit', () => setEngine('offline'))

  const shared = { go: setPage, setArt, status, refresh }

  return (
    <div className="app">
      <div className="backdrop" key={`${art.seed}-${art.hue}`}>
        <Shards seed={art.seed} hue={art.hue} />
      </div>

      <header className="topbar">
        <div className="brand">
          <Mark />
          <div>
            <b>RELIQUARY</b>
            <span>{t('brand.tag')} 0.1</span>
          </div>
        </div>
        <nav className="nav">
          {NAV.map(([id, Icon]) => (
            <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}>
              <Icon size={18} strokeWidth={1.8} />
              {t(`nav.${id}`)}
            </button>
          ))}
        </nav>
        <div className="top-right">
          <button className={`engine ${engine}`} onClick={refresh} title={t('engine.refresh')}>
            <i />
            {t(`engine.${engine}`)}
          </button>
          <div className="winbtns">
            <button onClick={() => api.window('minimize')} aria-label={t('window.minimize')}>
              <Minus size={15} />
            </button>
            <button onClick={() => api.window('maximize')} aria-label={t('window.maximize')}>
              <Square size={12} />
            </button>
            <button className="close" onClick={() => api.window('close')} aria-label={t('window.close')}>
              <X size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="page" key={page}>
        {page === 'home' && <Home {...shared} />}
        {page === 'operators' && <Operators {...shared} />}
        {page === 'armory' && <Armory {...shared} />}
        {page === 'vault' && <Vault {...shared} />}
        {page === 'settings' && <Settings {...shared} />}
      </main>
    </div>
  )
}

export type PageProps = {
  go: (page: Page) => void
  setArt: (art: Art) => void
  status: Status | null
  refresh: () => Promise<void>
}
