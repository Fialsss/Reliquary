import { useEffect, useState } from 'react'
import { Archive, ArrowRight, Blocks, CheckCircle2, ChevronLeft, ChevronRight, Cpu, Crosshair, FolderSearch, LogIn, Users } from 'lucide-react'
import type { PageProps, Page } from '../App'
import { api, basename, useCovers, type Season } from '../api'
import { hueOf, Mark, SeasonArt, Shards } from '../art'
import { useI18n } from '../i18n'
import { Avatar, useSession } from '../session'

const SLIDES = [
  { id: 'vault', seed: 41, hue: 196, page: 'vault', icon: Archive, alt: 'armory' },
  { id: 'operators', seed: 7, hue: 28, page: 'operators', icon: Users, alt: 'vault' },
  { id: 'armory', seed: 23, hue: 350, page: 'armory', icon: Crosshair, alt: 'vault' }
] as const
const SLIDE_MS = 8000

export default function Home({ go, setArt, status, openSeason }: PageProps) {
  const { t } = useI18n()
  const { profile, signIn } = useSession()
  const covers = useCovers()
  const [index, setIndex] = useState(0)
  const [seasons, setSeasons] = useState<Season[] | null>(null)
  const slide = SLIDES[index]

  useEffect(() => {
    setArt({ seed: slide.seed, hue: slide.hue })
    const timer = setTimeout(() => setIndex((index + 1) % SLIDES.length), SLIDE_MS)
    return () => clearTimeout(timer)
  }, [index])

  useEffect(() => {
    api.call<Season[]>('vault.seasons').then(setSeasons).catch(() => setSeasons([]))
  }, [])

  const step = (delta: number) => setIndex((index + delta + SLIDES.length) % SLIDES.length)
  const recent = (seasons ?? []).slice(-4).reverse()
  const inLibrary = (seasons ?? []).filter((s) => s.local > 0).length

  const store = status?.game.path.includes('steamapps') ? 'Steam' : status?.game.path ? 'Ubisoft Connect' : ''
  const checks = [
    {
      key: 'steam', icon: LogIn, ok: !!profile, fix: signIn,
      detail: profile ? profile.name : t('check.steam.hint')
    },
    {
      key: 'game', icon: FolderSearch, ok: status?.game.ok, fix: () => go('settings'),
      detail: store ? t('check.game.found', { store }) : t('check.game.hint')
    },
    {
      key: 'blender', icon: Blocks, ok: status?.blender.ok, fix: () => go('settings'),
      detail: status?.blender.version ? `Blender ${status.blender.version}` : t('check.blender.hint')
    },
    {
      key: 'oodle', icon: Cpu, ok: status?.oodle.ok, fix: () => go('settings'),
      detail: status?.oodle.path ? basename(status.oodle.path) : t('check.oodle.hint')
    }
  ]
  const missing = checks.filter((c) => !c.ok).length

  return (
    <div className="home">
      <section className="hero">
        <Shards className="hero-art" seed={slide.seed} hue={slide.hue} grain key={slide.id} />
        <div className="hero-veil" />
        <div className="hero-arrows">
          <button onClick={() => step(-1)} aria-label={t('home.prev')} data-tip={t('home.prev')}>
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => step(1)} aria-label={t('home.next')} data-tip={t('home.next')}>
            <svg className="ring" viewBox="0 0 36 36" key={index}>
              <circle cx="18" cy="18" r="16.5" style={{ animationDuration: `${SLIDE_MS}ms` }} />
            </svg>
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="hero-body" key={slide.id}>
          <span className="welcome" style={{ '--i': 0 } as React.CSSProperties}>
            <Mark size={14} /> {t('home.welcome')}
          </span>
          <div className="eyebrow" style={{ '--i': 1 } as React.CSSProperties}>
            {t(`slide.${slide.id}.eyebrow`)}
          </div>
          <h2 style={{ '--i': 2 } as React.CSSProperties}>
            {t(`slide.${slide.id}.title`)}
            <span>{t(`slide.${slide.id}.title2`)}</span>
          </h2>
          <p style={{ '--i': 3 } as React.CSSProperties}>{t(`slide.${slide.id}.body`)}</p>
          <div className="hero-actions" style={{ '--i': 4 } as React.CSSProperties}>
            <button className="btn primary" onClick={() => go(slide.page as Page)}>
              <slide.icon size={16} /> {t(`slide.${slide.id}.cta`)}
            </button>
            <button className="btn ghost" onClick={() => go(slide.alt as Page)}>
              {t(`nav.${slide.alt}`)} <ArrowRight size={15} />
            </button>
          </div>
        </div>
        <div className="hero-dots">
          {SLIDES.map((s, i) => (
            <button key={s.id} className={i === index ? 'on' : ''} onClick={() => setIndex(i)} aria-label={t(`slide.${s.id}.eyebrow`)} />
          ))}
        </div>
      </section>

      <aside className="home-side">
        <div className="card ready">
          <div className="ready-head">
            <div className="grow">
              <div className="label">{t('home.workspace')}</div>
              <b>{status == null ? '…' : missing ? t(missing === 1 ? 'home.fixOne' : 'home.fixMany', { n: missing }) : t('home.allReady')}</b>
            </div>
            <span className={`ready-count${missing ? '' : ' full'}`}>
              {checks.length - missing}/{checks.length}
            </span>
          </div>
          <div className="ready-bar" aria-hidden="true">
            {checks.map((c) => (
              <i key={c.key} className={status == null ? '' : c.ok ? 'ok' : 'todo'} />
            ))}
          </div>
          <ul className="checks">
            {checks.map(({ key, icon: Icon, ok, detail, fix }) => (
              <li key={key} className={ok ? 'ok' : ''}>
                <span className="check-icon">{key === 'steam' && profile ? <Avatar profile={profile} size={30} /> : <Icon size={16} strokeWidth={1.8} />}</span>
                <div className="grow">
                  <b>{t(`check.${key}`)}</b>
                  <small>{detail}</small>
                </div>
                {status == null ? null : ok ? (
                  <CheckCircle2 size={18} className="check-ok" aria-label={t('state.ready')} />
                ) : (
                  <button className="btn ghost small" onClick={fix}>
                    {t(key === 'steam' ? 'check.signIn' : 'check.set')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div className="card grow-card from-vault">
          <div className="from-vault-head">
            <div className="label">{t('home.fromVault')}</div>
            <span className="mono dim">{seasons ? t('home.seasonCount', { n: seasons.length, local: inLibrary }) : '…'}</span>
          </div>
          <div className="mini-covers">
            {recent.map((s) => (
              <button key={s.id} className="mini-cover" onClick={() => openSeason(s.id)}>
                <SeasonArt cover={covers[s.id]} seed={s.year * 10 + s.season} hue={hueOf(s.id)} />
                {s.local > 0 && <i className="mini-dot" aria-label={t('state.inLibrary')} />}
                <span>
                  <small className="mono">{s.id}</small>
                  <b>{s.name}</b>
                </span>
              </button>
            ))}
          </div>
          <button className="btn fill wide" onClick={() => go('vault')}>
            <Archive size={15} /> {t('home.openVault')}
          </button>
        </div>
      </aside>
    </div>
  )
}

