import { useEffect, useState } from 'react'
import { Archive, ArrowRight, Blocks, ChevronLeft, ChevronRight, Cpu, Crosshair, DownloadCloud, FolderSearch, Users } from 'lucide-react'
import type { PageProps, Page } from '../App'
import { api, basename, type Season } from '../api'
import { hueOf, Mark, Shards } from '../art'
import { useI18n } from '../i18n'

const SLIDES = [
  { id: 'vault', seed: 41, hue: 196, page: 'vault', icon: Archive, alt: 'armory' },
  { id: 'operators', seed: 7, hue: 28, page: 'operators', icon: Users, alt: 'vault' },
  { id: 'armory', seed: 23, hue: 350, page: 'armory', icon: Crosshair, alt: 'vault' }
] as const
const SLIDE_MS = 8000

export default function Home({ go, setArt, status }: PageProps) {
  const { t } = useI18n()
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

  const checks = [
    { key: 'game', icon: FolderSearch, ok: status?.game.ok, detail: status?.game.path && basename(status.game.path) },
    { key: 'oodle', icon: Cpu, ok: status?.oodle.ok, detail: status?.oodle.path && basename(status.oodle.path) },
    { key: 'blender', icon: Blocks, ok: status?.blender.ok, detail: status?.blender.version && `Blender ${status.blender.version}` },
    { key: 'depot', icon: DownloadCloud, ok: status?.depot.ok, detail: 'DepotDownloader 3.4' }
  ]

  return (
    <div className="home">
      <section className="hero">
        <Shards className="hero-art" seed={slide.seed} hue={slide.hue} grain key={slide.id} />
        <div className="hero-veil" />
        <div className="hero-arrows">
          <button onClick={() => step(-1)} aria-label={t('home.prev')}>
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => step(1)} aria-label={t('home.next')}>
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
        <div className="card">
          <div className="label">{t('home.workspace')}</div>
          <ul className="rows">
            {checks.map(({ key, icon: Icon, ok, detail }) => (
              <li key={key}>
                <span className="tile-icon">
                  <Icon size={17} strokeWidth={1.8} />
                </span>
                <div className="grow">
                  <b>{t(`check.${key}`)}</b>
                  <small>{detail || t(`check.${key}.hint`)}</small>
                </div>
                <span className={`state ${status == null ? 'muted' : ok ? 'ok' : key === 'depot' ? 'info' : 'warn'}`}>
                  {status == null ? '…' : ok ? t('state.ready') : key === 'depot' ? t('state.onDemand') : t('state.missing')}
                </span>
              </li>
            ))}
          </ul>
          <button className="btn fill wide" onClick={() => go('settings')}>
            {t('home.openSettings')}
          </button>
        </div>

        <div className="card grow-card">
          <div className="card-title">
            <span className="tile-icon">
              <Archive size={17} strokeWidth={1.8} />
            </span>
            <b>{t('home.latestSeasons')}</b>
          </div>
          <ul className="rows">
            {recent.map((s) => (
              <li key={s.id} className="link" onClick={() => go('vault')}>
                <Shards className="thumb" seed={s.year * 10 + s.season} hue={hueOf(s.id)} />
                <div className="grow">
                  <b>{s.name}</b>
                  <small className="mono">
                    {s.id} · {s.patches.at(-1)!.date}
                  </small>
                </div>
                <span className={`state ${s.local ? 'ok' : 'info'}`}>{s.local ? t('state.inLibrary') : t('state.onSteam')}</span>
              </li>
            ))}
          </ul>
          <div className="card-foot">
            <span>{seasons ? t('home.seasonCount', { n: seasons.length, local: inLibrary }) : '…'}</span>
            <button className="link-btn" onClick={() => go('vault')}>
              {t('home.openVault')}
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
