import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronLeft, ChevronRight, DownloadCloud, FolderOpen, ListTree, LogIn, Search, Smartphone, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, bytes, useCovers, useEngineEvent, type DepotFile, type Patch, type Season } from '../api'
import { hueOf, SeasonArt } from '../art'
import { useI18n } from '../i18n'
import { Avatar, useSession } from '../session'
import { Check, Chip, ConfirmButton, PageHead, Segmented, Spinner } from '../ui'

const seedOf = (s: Season) => s.year * 10 + s.season

export default function Vault({ setArt, focus, openSeason }: PageProps) {
  const { t } = useI18n()
  const covers = useCovers()
  const [seasons, setSeasons] = useState<Season[] | null>(null)
  const [error, setError] = useState('')
  const [year, setYear] = useState('all')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Season | null>(null)

  const load = () => api.call<Season[]>('vault.seasons').then(setSeasons).catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    const match = focus && seasons?.find((s) => s.id === focus)
    if (!match) return
    setArt({ seed: seedOf(match), hue: hueOf(match.id), image: covers[match.id] })
    setOpen(match)
    openSeason(null)
  }, [focus, seasons, covers])

  const years = useMemo(() => [...new Set((seasons ?? []).map((s) => s.year))], [seasons])
  const shown = (seasons ?? []).filter(
    (s) => (year === 'all' || s.year === Number(year)) && `${s.id} ${s.name}`.toLowerCase().includes(query.toLowerCase())
  )

  if (open) {
    return (
      <SeasonDetail
        season={open}
        back={() => {
          setOpen(null)
          load()
        }}
        setArt={setArt}
        cover={covers[open.id]}
      />
    )
  }

  return (
    <div className="stack">
      <PageHead
        eyebrow={t('vault.eyebrow')}
        title={t('vault.title')}
        sub={t('vault.sub')}
        right={
          <label className="search">
            <Search size={15} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('vault.search')} />
          </label>
        }
      />
      <div className="years">
        <Segmented value={year} onChange={setYear} options={[['all', t('vault.all')], ...years.map((y): [string, string] => [String(y), `Y${y}`])]} />
      </div>
      {error && <Notice text={t(error)} />}
      {!seasons && !error && (
        <div className="center">
          <Spinner size={22} />
        </div>
      )}
      <div className="grid tiles">
        {shown.map((s, i) => (
          <button
            key={s.id}
            className="tile"
            style={{ '--i': Math.min(i, 12), '--hue': hueOf(s.id) } as React.CSSProperties}
            onClick={() => {
              setArt({ seed: seedOf(s), hue: hueOf(s.id), image: covers[s.id] })
              setOpen(s)
            }}
          >
            <div className="cover">
              <SeasonArt cover={covers[s.id]} seed={seedOf(s)} hue={hueOf(s.id)} />
            </div>
            <div className="tile-body">
              <span className="mono dim">{s.id}</span>
              <b>{s.name}</b>
              <small>{s.patches.at(-1)!.date}</small>
              <span className="tile-foot">
                {s.local ? <Chip tone="ok">{t('state.inLibrary')}</Chip> : <Chip tone="info">{t('state.onSteam')}</Chip>}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function Notice({ text, onClose }: { text: string; onClose?: () => void }) {
  return (
    <div className="notice">
      <AlertTriangle size={16} />
      <span>{text}</span>
      {onClose && (
        <button onClick={onClose} aria-label="Dismiss">
          <X size={14} />
        </button>
      )}
    </div>
  )
}

const CATEGORIES = ['data', 'textures', 'meshes', 'other'] as const

function SeasonDetail({ season, back, setArt, cover }: { season: Season; back: () => void; setArt: PageProps['setArt']; cover?: string }) {
  const { t } = useI18n()
  const { profile, job, signIn } = useSession()
  const [patch, setPatch] = useState<Patch>(season.patches.at(-1)!)
  const [files, setFiles] = useState<DepotFile[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [listing, setListing] = useState(false)
  const [phase, setPhase] = useState('')
  const [log, setLog] = useState('')
  const [error, setError] = useState('')
  const [gallery, setGallery] = useState<string[]>([])
  const [viewing, setViewing] = useState<number | null>(null)

  const here = job?.season === season.id && job.manifest === patch.manifest
  const load = (refresh = false) =>
    api.call<DepotFile[]>('vault.files', { season: season.id, manifest: patch.manifest, refresh }).then(setFiles)

  useEffect(() => {
    setArt({ seed: seedOf(season), hue: hueOf(season.id), image: cover })
    api.call<string[]>('art.gallery', { season: season.id }).then(setGallery).catch(() => undefined)
  }, [])
  useEffect(() => {
    setFiles(null)
    setPicked(new Set())
  }, [patch])

  useEngineEvent<{ key: string }>('steam.status', (d) => setPhase(d.key))
  useEngineEvent<string>('vault.log', setLog)
  useEngineEvent<{ season: string; manifest: string; ok: boolean }>('vault.ended', (d) => {
    if (d.season !== season.id || d.manifest !== patch.manifest) return
    load().catch(() => undefined)
    if (d.ok) setPicked(new Set())
  })

  const listFiles = async () => {
    setListing(true)
    setError('')
    setPhase('')
    setLog('')
    try {
      await load()
    } catch (e) {
      if ((e as Error).message !== 'Cancelled') setError((e as Error).message)
    } finally {
      setListing(false)
    }
  }

  // runs in the background: the top bar follows it on every page, and the session announces the end
  const download = () => {
    setError('')
    api
      .call('vault.download', { season: season.id, manifest: patch.manifest, files: [...picked] })
      .catch((e: Error) => e.message !== 'Cancelled' && setError(e.message))
  }

  const openFolder = async () => api.open(await api.call<string>('vault.folder', { season: season.id, manifest: patch.manifest }))

  const toggle = (name: string) => {
    const next = new Set(picked)
    next.has(name) ? next.delete(name) : next.add(name)
    setPicked(next)
  }
  const toggleCategory = (category: DepotFile['category']) => {
    const names = (files ?? []).filter((f) => f.category === category).map((f) => f.name)
    const all = names.every((n) => picked.has(n))
    const next = new Set(picked)
    names.forEach((n) => (all ? next.delete(n) : next.add(n)))
    setPicked(next)
  }

  const size = (files ?? []).filter((f) => picked.has(f.name)).reduce((sum, f) => sum + f.size, 0)
  const hasLocal = (files ?? []).some((f) => f.local)
  const localSize = (files ?? []).filter((f) => f.local).reduce((sum, f) => sum + f.size, 0)

  return (
    <div className="detail">
      <aside className="detail-side">
        <button className="back" onClick={back}>
          <ArrowLeft size={15} /> {t('vault.back')}
        </button>
        <div className="detail-cover">
          <SeasonArt cover={cover} seed={seedOf(season)} hue={hueOf(season.id)} />
          <div className="detail-cover-text">
            <span className="mono">{season.id}</span>
            <b>{season.name}</b>
          </div>
        </div>
        <dl className="specs">
          <dt>{t('vault.released')}</dt>
          <dd>{patch.date}</dd>
          {season.patches.length > 1 && (
            <>
              <dt>{t('vault.build')}</dt>
              <dd>
                <Segmented
                  value={patch.manifest}
                  onChange={(m) => setPatch(season.patches.find((p) => p.manifest === m)!)}
                  options={season.patches.map((p): [string, string] => [p.manifest, p.date.slice(5)])}
                />
              </dd>
            </>
          )}
          <dt>{t('vault.manifest')}</dt>
          <dd className="mono">{patch.manifest}</dd>
          <dt>{t('vault.depot')}</dt>
          <dd className="mono">359550 / 359551</dd>
        </dl>
        {gallery.length > 0 && (
          <div className="gallery">
            <div className="label">{t('vault.gallery', { n: gallery.length })}</div>
            <div className="gallery-grid">
              {gallery.map((url, i) => (
                <button key={url} onClick={() => setViewing(i)} aria-label={t('vault.viewImage', { n: i + 1 })}>
                  <img src={url} alt="" loading="lazy" draggable={false} onError={() => setGallery((all) => all.filter((u) => u !== url))} />
                </button>
              ))}
            </div>
          </div>
        )}
        {viewing !== null && <Lightbox images={gallery} index={viewing} setIndex={setViewing} />}
      </aside>

      <section className="detail-main">
        <div className="card steam">
          <div className="steam-row">
            {listing ? (
              <span className="tile-icon">
                <Spinner />
              </span>
            ) : profile ? (
              <Avatar profile={profile} size={38} />
            ) : (
              <span className="tile-icon">
                <Smartphone size={17} strokeWidth={1.8} />
              </span>
            )}
            <div className="grow">
              <b>{listing ? t(`steam.phase.${phase || 'connecting'}`) : profile ? t('steam.signedIn', { user: profile.name }) : t('steam.signedOut')}</b>
              <small className={listing ? 'mono' : ''}>{listing ? log || '…' : profile ? t('steam.remembered') : t('steam.signedOutBody')}</small>
            </div>
            {!profile && !listing && (
              <button className="btn primary small" onClick={signIn}>
                <LogIn size={14} /> {t('account.signIn')}
              </button>
            )}
          </div>
        </div>

        {error && <Notice text={t(error)} onClose={() => setError('')} />}

        <div className="card files">
          <div className="files-head">
            <div>
              <div className="label">{t('vault.archives')}</div>
              {files && <small>{t('vault.fileCount', { n: files.length })}</small>}
            </div>
            {files && (
              <div className="presets">
                {CATEGORIES.filter((c) => files.some((f) => f.category === c)).map((c) => (
                  <button key={c} className="btn ghost small" onClick={() => toggleCategory(c)}>
                    {t(`cat.${c}`)}
                  </button>
                ))}
              </div>
            )}
          </div>

          {!files ? (
            <div className="files-empty">
              <ListTree size={26} strokeWidth={1.5} />
              <p>{t('vault.listHint')}</p>
              <button className="btn primary" onClick={listFiles} disabled={listing || !!job}>
                {listing ? <Spinner /> : <ListTree size={16} />} {t('vault.listFiles')}
              </button>
            </div>
          ) : (
            <ul className="file-list">
              {files.map((f) => (
                <li key={f.name} className={picked.has(f.name) ? 'on' : ''} onClick={() => toggle(f.name)}>
                  <Check checked={picked.has(f.name)} onChange={() => toggle(f.name)} label={f.name} />
                  <span className="mono grow">{f.name}</span>
                  {f.local && <CheckCircle2 size={14} className="ok-icon" aria-label={t('state.inLibrary')} />}
                  <Chip tone={f.category === 'textures' ? 'info' : f.category === 'meshes' ? 'warn' : 'muted'} dot={false}>
                    {t(`cat.${f.category}`)}
                  </Chip>
                  <span className="mono size">{bytes(f.size)}</span>
                </li>
              ))}
            </ul>
          )}

          {here && (
            <div className="progress">
              <div className="bar">
                <i style={{ width: `${job.percent}%` }} />
              </div>
              <div className="progress-text">
                <span className="mono">{job.file || t('steam.phase.connecting')}</span>
                <b>{job.percent.toFixed(1)}%</b>
              </div>
            </div>
          )}

          {files && (
            <div className="files-foot">
              <span>{picked.size ? t('vault.selected', { n: picked.size, size: bytes(size) }) : t('vault.nothingSelected')}</span>
              <div className="row">
                {hasLocal && !here && (
                  <ConfirmButton
                    small={false}
                    label={t('vault.deleteLocal', { size: bytes(localSize) })}
                    confirm={t('storage.confirm')}
                    onConfirm={() =>
                      api
                        .call('vault.delete', { season: season.id, manifest: patch.manifest })
                        .then(() => load())
                        .catch((e: Error) => setError(e.message))
                    }
                  />
                )}
                {hasLocal && (
                  <button className="btn ghost" onClick={openFolder}>
                    <FolderOpen size={15} /> {t('vault.openFolder')}
                  </button>
                )}
                {here ? (
                  <button className="btn ghost" onClick={() => api.call('vault.cancel')}>
                    <X size={15} /> {t('vault.cancel')}
                  </button>
                ) : (
                  <button className="btn primary" onClick={download} disabled={!picked.size || !!job || listing}>
                    <DownloadCloud size={16} /> {t('vault.download')}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

/** Full-window image viewer: arrows or ←/→ to move, Esc or a click outside to close. */
function Lightbox({ images, index, setIndex }: { images: string[]; index: number; setIndex: (i: number | null) => void }) {
  const { t } = useI18n()
  const step = (delta: number) => setIndex((index + delta + images.length) % images.length)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIndex(null)
      if (e.key === 'ArrowRight') step(1)
      if (e.key === 'ArrowLeft') step(-1)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [index])
  return (
    <div className="lightbox" onMouseDown={(e) => e.target === e.currentTarget && setIndex(null)}>
      <img src={images[index]} alt="" key={images[index]} />
      <button className="lb-close" onClick={() => setIndex(null)} aria-label={t('window.close')} data-tip={t('window.close')} data-tip-side="left">
        <X size={18} />
      </button>
      {images.length > 1 && (
        <>
          <button className="lb-nav prev" onClick={() => step(-1)} aria-label={t('home.prev')}>
            <ChevronLeft size={22} />
          </button>
          <button className="lb-nav next" onClick={() => step(1)} aria-label={t('home.next')}>
            <ChevronRight size={22} />
          </button>
          <span className="lb-count mono">
            {index + 1} / {images.length}
          </span>
        </>
      )}
    </div>
  )
}
