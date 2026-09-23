import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ExternalLink, FolderOpen, Info, LogIn, LogOut, Smartphone, X } from 'lucide-react'
import { api, useEngineEvent, type Settings } from './api'
import { useI18n, type Lang } from './i18n'
import { Segmented, Spinner, type Tone } from './ui'

export type Profile = { user: string; steamid: string; name: string; avatar: string }
export type Job = { season: string; manifest: string; files: number; percent: number; file: string }
type Toast = { id: number; text: string; tone: Tone }
type Login = { open: boolean; qr: string[] | null; phase: string; error: string; done: boolean }

type Session = {
  profile: Profile | null
  job: Job | null
  signIn: () => void
  signOut: () => Promise<void>
  toast: (text: string, tone?: Tone) => void
}

const Context = createContext<Session | null>(null)
export const useSession = () => useContext(Context)!

const CLOSED: Login = { open: false, qr: null, phase: '', error: '', done: false }

/** Steam account, background downloads and notifications, shared by every page. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [login, setLogin] = useState<Login>(CLOSED)
  const nextToast = useRef(1)

  const toast = useCallback((text: string, tone: Tone = 'info') => {
    const id = nextToast.current++
    setToasts((all) => [...all, { id, text, tone }])
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), 5000)
  }, [])

  useEffect(() => {
    api.call<Profile | null>('steam.profile').then(setProfile).catch(() => undefined)
  }, [])

  const welcome = (p: Profile | null) => {
    setProfile(p)
    setLogin((l) => ({ ...l, qr: null, done: true }))
    setTimeout(() => setLogin(CLOSED), 1400)
  }

  const signIn = () => {
    setLogin({ ...CLOSED, open: true })
    api
      .call<Profile | null>('steam.login')
      .then(welcome)
      .catch((e: Error) => setLogin((l) => (l.open ? { ...l, qr: null, error: e.message } : l)))
  }

  const signOut = async () => {
    await api.call<Settings>('steam.signout')
    setProfile(null)
    toast(t('toast.signedOut'), 'muted')
  }

  // Steam can ask for a scan in the middle of any job: the dialog opens by itself.
  useEngineEvent<{ matrix: string[] }>('steam.qr', (d) => setLogin((l) => ({ ...l, open: true, qr: d.matrix, error: '' })))
  useEngineEvent<{ key: string }>('steam.status', (d) => setLogin((l) => ({ ...l, phase: d.key })))
  useEngineEvent('steam.signed_in', () => {
    api.call<Profile | null>('steam.profile', { refresh: true }).then((p) => {
      setProfile(p)
      if (p) toast(t('toast.welcome', { name: p.name }), 'ok')
      setLogin((l) => (l.open && l.qr ? { ...l, qr: null, done: true } : l))
      setTimeout(() => setLogin((l) => (l.done ? CLOSED : l)), 1400)
    })
  })

  useEngineEvent<Omit<Job, 'percent' | 'file'>>('vault.started', (d) => setJob({ ...d, percent: 0, file: '' }))
  useEngineEvent<{ percent: number; file: string }>('vault.progress', (d) => setJob((j) => (j ? { ...j, ...d } : j)))
  useEngineEvent<{ season: string; ok: boolean; cancelled: boolean }>('vault.ended', (d) => {
    setJob(null)
    if (d.ok) toast(t('toast.done', { season: d.season }), 'ok')
    else if (d.cancelled) toast(t('toast.cancelled', { season: d.season }), 'muted')
    else toast(t('toast.failed', { season: d.season }), 'bad')
  })
  useEngineEvent('engine.exit', () => toast(t('toast.engineOffline'), 'bad'))

  return (
    <Context.Provider value={{ profile, job, signIn, signOut, toast }}>
      {children}
      {login.open && (
        <LoginDialog
          login={login}
          profile={profile}
          retry={signIn}
          close={() => {
            api.call('vault.cancel')
            setLogin(CLOSED)
          }}
        />
      )}
      <div className="toasts" aria-live="polite">
        {toasts.map((x) => (
          <div key={x.id} className={`toast ${x.tone}`}>
            {x.tone === 'ok' ? <CheckCircle2 size={16} /> : x.tone === 'bad' ? <AlertTriangle size={16} /> : <Info size={16} />}
            <span>{x.text}</span>
          </div>
        ))}
      </div>
    </Context.Provider>
  )
}

function LoginDialog({ login, profile, retry, close }: { login: Login; profile: Profile | null; retry: () => void; close: () => void }) {
  const { t } = useI18n()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !login.done && close()
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [login.done])

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !login.done && close()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={t('login.title')}>
        {!login.done && (
          <button className="dialog-close" onClick={close} aria-label={t('window.close')}>
            <X size={16} />
          </button>
        )}
        {login.done ? (
          <div className="login-done">
            <Avatar profile={profile} size={84} />
            <b>{t('login.welcome', { name: profile?.name ?? '' })}</b>
            <small>{t('login.ready')}</small>
          </div>
        ) : login.error ? (
          <div className="login-state">
            <span className="tile-icon warn">
              <AlertTriangle size={18} />
            </span>
            <b>{t('login.failed')}</b>
            <p className="mono">{login.error}</p>
            <button className="btn primary" onClick={retry}>
              {t('common.retry')}
            </button>
          </div>
        ) : login.qr ? (
          <>
            <div className="label">{t('login.title')}</div>
            <div className="login-qr">
              <QrCode matrix={login.qr} />
            </div>
            <ol className="login-steps">
              <li>{t('login.step1')}</li>
              <li>{t('login.step2')}</li>
              <li>{t('login.step3')}</li>
            </ol>
            <span className="chip info dot">
              <Smartphone size={12} /> {t('steam.waiting')}
            </span>
          </>
        ) : (
          <div className="login-state">
            <Spinner size={28} />
            <b>{t(`steam.phase.${login.phase || 'connecting'}`)}</b>
            <small>{t('login.owns')}</small>
          </div>
        )}
      </div>
    </div>
  )
}

export function QrCode({ matrix }: { matrix: string[] }) {
  const size = matrix.length
  const cells = matrix.flatMap((row, y) => [...row].map((c, x) => (c === '1' ? `M${x} ${y}h1v1h-1z` : '')))
  return (
    <svg viewBox={`-2 -2 ${size + 4} ${size + 4}`} shapeRendering="crispEdges" role="img" aria-label="Steam sign-in QR code">
      <rect x="-2" y="-2" width={size + 4} height={size + 4} fill="#fff" />
      <path d={cells.join('')} fill="#0b0b0d" />
    </svg>
  )
}

export function Avatar({ profile, size = 30 }: { profile: Profile | null; size?: number }) {
  const initial = (profile?.name || profile?.user || '?').slice(0, 1).toUpperCase()
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.42 }}>
      {profile?.avatar ? <img src={profile.avatar} alt="" /> : initial}
    </span>
  )
}

/** The pill in the top bar: sign-in button, or the Steam profile with its menu. */
export function AccountPill() {
  const { t, lang, setLang } = useI18n()
  const { profile, signIn, signOut } = useSession()
  const [open, setOpen] = useState(false)
  const menu = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => !menu.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    addEventListener('mousedown', onDown)
    addEventListener('keydown', onKey)
    return () => {
      removeEventListener('mousedown', onDown)
      removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!profile) {
    return (
      <button className="account signin" onClick={signIn} data-tip={t('account.signIn')}>
        <LogIn size={16} /> {t('check.signIn')}
      </button>
    )
  }

  const openLibrary = async () => api.open((await api.call<Settings>('settings.get')).library)

  return (
    <div className="account-wrap" ref={menu}>
      <button className={`account${open ? ' open' : ''}`} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="avatar-dot">
          <Avatar profile={profile} />
        </span>
        <span className="account-text">
          <b>{profile.name}</b>
          <small>Steam</small>
        </span>
        <ChevronDown size={15} className="chev" />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <Avatar profile={profile} size={46} />
            <div className="grow">
              <b>{profile.name}</b>
              <small>@{profile.user}</small>
              {profile.steamid && <small className="mono">{profile.steamid}</small>}
            </div>
          </div>
          {profile.steamid && (
            <a className="menu-item" role="menuitem" href={`https://steamcommunity.com/profiles/${profile.steamid}`} target="_blank" rel="noreferrer">
              <ExternalLink size={15} /> {t('account.profile')}
            </a>
          )}
          <button className="menu-item" role="menuitem" onClick={openLibrary}>
            <FolderOpen size={15} /> {t('account.library')}
          </button>
          <div className="menu-row">
            <span>{t('setting.language')}</span>
            <Segmented<Lang> value={lang} onChange={setLang} options={[['it', 'IT'], ['en', 'EN']]} />
          </div>
          <button
            className="menu-item danger"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              signOut()
            }}
          >
            <LogOut size={15} /> {t('steam.signOut')}
          </button>
        </div>
      )}
    </div>
  )
}

/** A download running in the background, visible from every page. */
export function JobChip({ onOpen }: { onOpen: () => void }) {
  const { job } = useSession()
  if (!job) return null
  const dash = 2 * Math.PI * 9
  return (
    <button className="job" onClick={onOpen} data-tip={job.file || job.season}>
      <svg viewBox="0 0 22 22" width="20" height="20">
        <circle cx="11" cy="11" r="9" className="job-track" />
        <circle cx="11" cy="11" r="9" className="job-fill" strokeDasharray={dash} strokeDashoffset={dash * (1 - job.percent / 100)} />
      </svg>
      <span className="mono">{job.season}</span>
      <b>{job.percent.toFixed(0)}%</b>
    </button>
  )
}
