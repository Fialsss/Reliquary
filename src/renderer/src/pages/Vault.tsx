import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, CheckCircle2, DownloadCloud, FolderOpen, ListTree, LogOut, Search, Smartphone, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, bytes, useEngineEvent, type DepotFile, type Patch, type Season, type Settings } from '../api'
import { hueOf, Shards } from '../art'
import { useI18n } from '../i18n'
import { Check, Chip, PageHead, Segmented, Spinner } from '../ui'

const seedOf = (s: Season) => s.year * 10 + s.season

export default function Vault({ setArt }: PageProps) {
  const { t } = useI18n()
  const [seasons, setSeasons] = useState<Season[] | null>(null)
  const [error, setError] = useState('')
  const [year, setYear] = useState('all')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Season | null>(null)

  const load = () => api.call<Season[]>('vault.seasons').then(setSeasons).catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

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
      {error && <Notice text={error} />}
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
            style={{ '--i': Math.min(i, 12) } as React.CSSProperties}
            onClick={() => {
              setArt({ seed: seedOf(s), hue: hueOf(s.id) })
              setOpen(s)
            }}
          >
            <div className="cover">
              <Shards seed={seedOf(s)} hue={hueOf(s.id)} />
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

function SeasonDetail({ season, back, setArt }: { season: Season; back: () => void; setArt: PageProps['setArt'] }) {
  const { t } = useI18n()
  const [patch, setPatch] = useState<Patch>(season.patches.at(-1)!)
  const [files, setFiles] = useState<DepotFile[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<'files' | 'download' | null>(null)
  const [qr, setQr] = useState<string[] | null>(null)
  const [phase, setPhase] = useState('')
  const [log, setLog] = useState('')
  const [progress, setProgress] = useState<{ percent: number; file: string } | null>(null)
  const [error, setError] = useState('')
  const [user, setUser] = useState('')

  useEffect(() => {
    setArt({ seed: seedOf(season), hue: hueOf(season.id) })
    api.call<Settings>('settings.get').then((s) => setUser(s.steam_user))
  }, [])
  useEffect(() => {
    setFiles(null)
    setPicked(new Set())
  }, [patch])

  useEngineEvent<{ matrix: string[] }>('vault.qr', (d) => setQr(d.matrix))
  useEngineEvent<{ key: string }>('vault.status', (d) => setPhase(d.key))
  useEngineEvent<string>('vault.log', setLog)
  useEngineEvent<{ percent: number; file: string }>('vault.progress', (d) => {
    setQr(null)
    setProgress(d)
  })
  useEngineEvent<{ user: string }>('vault.signed_in', (d) => {
    setQr(null)
    setUser(d.user)
  })

  const run = async (kind: 'files' | 'download', job: () => Promise<void>) => {
    setBusy(kind)
    setError('')
    setPhase('')
    setLog('')
    try {
      await job()
    } catch (e) {
      const message = (e as Error).message
      if (message !== 'Cancelled') setError(message)
    } finally {
      setBusy(null)
      setQr(null)
      setProgress(null)
    }
  }

  const listFiles = () =>
    run('files', async () => {
      setFiles(await api.call<DepotFile[]>('vault.files', { season: season.id, manifest: patch.manifest }))
    })

  const download = () =>
    run('download', async () => {
      await api.call('vault.download', { season: season.id, manifest: patch.manifest, files: [...picked] })
      setFiles(await api.call<DepotFile[]>('vault.files', { season: season.id, manifest: patch.manifest }))
      setPicked(new Set())
    })

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

  return (
    <div className="detail">
      <aside className="detail-side">
        <button className="back" onClick={back}>
          <ArrowLeft size={15} /> {t('vault.back')}
        </button>
        <div className="detail-cover">
          <Shards seed={seedOf(season)} hue={hueOf(season.id)} grain />
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
      </aside>

      <section className="detail-main">
        <div className="card steam">
          {qr ? (
            <div className="qr-row">
              <QrCode matrix={qr} />
              <div>
                <div className="label">{t('steam.scanTitle')}</div>
                <p>{t('steam.scanBody')}</p>
                <Chip tone="info">
                  <Smartphone size={12} /> {t('steam.waiting')}
                </Chip>
              </div>
            </div>
          ) : (
            <div className="steam-row">
              <span className="tile-icon">
                {busy ? <Spinner /> : user ? <CheckCircle2 size={17} /> : <Smartphone size={17} strokeWidth={1.8} />}
              </span>
              <div className="grow">
                <b>{busy ? t(`steam.phase.${phase || 'connecting'}`) : user ? t('steam.signedIn', { user }) : t('steam.signedOut')}</b>
                <small className={busy ? 'mono' : ''}>{busy ? log || '…' : user ? t('steam.remembered') : t('steam.signedOutBody')}</small>
              </div>
              {user && !busy && (
                <button
                  className="btn ghost small"
                  onClick={() => api.call('vault.signout').then(() => setUser(''))}
                >
                  <LogOut size={14} /> {t('steam.signOut')}
                </button>
              )}
            </div>
          )}
        </div>

        {error && <Notice text={error} onClose={() => setError('')} />}

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
              <button className="btn primary" onClick={listFiles} disabled={busy !== null}>
                {busy === 'files' ? <Spinner /> : <ListTree size={16} />} {t('vault.listFiles')}
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

          {progress && (
            <div className="progress">
              <div className="bar">
                <i style={{ width: `${progress.percent}%` }} />
              </div>
              <div className="progress-text">
                <span className="mono">{progress.file}</span>
                <b>{progress.percent.toFixed(1)}%</b>
              </div>
            </div>
          )}

          {files && (
            <div className="files-foot">
              <span>{picked.size ? t('vault.selected', { n: picked.size, size: bytes(size) }) : t('vault.nothingSelected')}</span>
              <div className="row">
                {hasLocal && (
                  <button className="btn ghost" onClick={openFolder}>
                    <FolderOpen size={15} /> {t('vault.openFolder')}
                  </button>
                )}
                {busy === 'download' ? (
                  <button className="btn ghost" onClick={() => api.call('vault.cancel')}>
                    <X size={15} /> {t('vault.cancel')}
                  </button>
                ) : (
                  <button className="btn primary" onClick={download} disabled={!picked.size || busy !== null}>
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

function QrCode({ matrix }: { matrix: string[] }) {
  const size = matrix.length
  const cells = matrix.flatMap((row, y) => [...row].map((c, x) => (c === '1' ? `M${x} ${y}h1v1h-1z` : '')))
  return (
    <div className="qr">
      <svg viewBox={`-2 -2 ${size + 4} ${size + 4}`} shapeRendering="crispEdges" role="img" aria-label="Steam sign-in QR code">
        <path d={cells.join('')} fill="#0b0b0d" />
      </svg>
    </div>
  )
}
