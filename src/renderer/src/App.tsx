import { useCallback, useEffect, useState } from 'react'
import { Archive, CircleHelp, Copy, Crosshair, House, Minus, SlidersHorizontal, Square, Users, X } from 'lucide-react'
import { api, useEngineEvent, type Status } from './api'
import { Mark, SeasonArt } from './art'
import { useI18n } from './i18n'
import Home from './pages/Home'
import Vault from './pages/Vault'
import Operators from './pages/Operators'
import Armory from './pages/Armory'
import Settings from './pages/Settings'
import { AccountPill, JobChip } from './session'
import Tour from './Tour'

export type Page = 'home' | 'operators' | 'armory' | 'vault' | 'settings'
export type Art = { seed: number; hue: number; image?: string }

const NAV = [
  ['home', House],
  ['operators', Users],
  ['armory', Crosshair],
  ['vault', Archive],
  ['settings', SlidersHorizontal]
] as const

type Motion = '' | 'closing' | 'minimizing' | 'settle'

function firstPage(): Page {
  const hash = location.hash.slice(1)
  return NAV.some(([id]) => id === hash) ? (hash as Page) : 'home'
}

// The guided tour opens by itself on the very first launch.
function firstLaunch(): boolean {
  try {
    if (localStorage.getItem('tourSeen')) return false
    localStorage.setItem('tourSeen', '1')
  } catch {
    return false
  }
  return true
}

export default function App() {
  const { t } = useI18n()
  const [page, setPage] = useState<Page>(firstPage)
  const [art, setArt] = useState<Art>({ seed: 41, hue: 196 })
  const [engine, setEngine] = useState<'starting' | 'ready' | 'offline'>('starting')
  const [status, setStatus] = useState<Status | null>(null)
  const [motion, setMotion] = useState<Motion>('')
  const [maximized, setMaximized] = useState(false)
  const [tour, setTour] = useState(firstLaunch)
  const [focus, setFocus] = useState<string | null>(null)

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

  // The window fades itself; the page adds depth: shrink on exit, settle on return.
  useEffect(
    () =>
      api.onWindow((state) => {
        if (state === 'closing' || state === 'minimizing') return setMotion(state)
        if (state === 'maximize' || state === 'unmaximize') setMaximized(state === 'maximize')
        setMotion('settle')
        setTimeout(() => setMotion(''), 420)
      }),
    []
  )

  const openSeason = (id: string | null) => {
    setFocus(id)
    if (id) setPage('vault')
  }
  const shared = { go: setPage, setArt, status, refresh, focus, openSeason, startTour: () => setTour(true) }

  return (
    <div className={`app ${motion}`}>
      <div className="backdrop" key={`${art.seed}-${art.hue}-${art.image ?? ''}`}>
        <SeasonArt cover={art.image} seed={art.seed} hue={art.hue} />
      </div>

      <header className="topbar">
        <div className="brand">
          <Mark />
          <div>
            <b>RELIQUARY</b>
            <span>{t('brand.tag')} {__VERSION__.replace(/\.0$/, '')}</span>
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
          {engine === 'offline' && (
            <button className="engine offline" onClick={refresh} data-tip={t('engine.refresh')}>
              <i />
              {t('engine.offline')}
            </button>
          )}
          <JobChip onOpen={() => setPage('vault')} />
          <button className={`help${tour ? ' active' : ''}`} onClick={() => setTour(true)} data-tip={t('nav.guide')} aria-label={t('nav.guide')}>
            <CircleHelp size={18} strokeWidth={1.8} />
          </button>
          <AccountPill />
          <div className="winbtns">
            <button onClick={() => api.window('minimize')} aria-label={t('window.minimize')} data-tip={t('window.minimize')}>
              <Minus size={15} />
            </button>
            <button onClick={() => api.window('maximize')} aria-label={t(maximized ? 'window.restore' : 'window.maximize')} data-tip={t(maximized ? 'window.restore' : 'window.maximize')}>
              {maximized ? <Copy size={12} /> : <Square size={12} />}
            </button>
            <button className="close" onClick={() => api.window('close')} aria-label={t('window.close')} data-tip={t('window.close')} data-tip-side="left">
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
      {tour && <Tour go={setPage} close={() => setTour(false)} />}
    </div>
  )
}

export type PageProps = {
  go: (page: Page) => void
  setArt: (art: Art) => void
  status: Status | null
  refresh: () => Promise<void>
  /** a season the Vault should open straight away (null once it has) */
  focus: string | null
  openSeason: (id: string | null) => void
  startTour: () => void
}
