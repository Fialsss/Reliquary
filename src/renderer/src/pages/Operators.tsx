import { useEffect, useState } from 'react'
import { Box, Check, ChevronRight, Cpu, Database, Download, FolderOpen, FolderSearch, RefreshCw, Search, Users, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, bytes, useEngineEvent, type Operator } from '../api'
import { hueOf, Shards } from '../art'
import { useI18n } from '../i18n'
import { useSession } from '../session'
import { PageHead, Spinner } from '../ui'

type Read = { state: 'waiting' | 'reading' | 'ok' | 'outdated' | 'failed'; operators?: Operator[]; error?: string }
type Index = { indexed: boolean; bytes: number; exports: string; busy: boolean }
type Progress = { step: 'index' | 'export'; uid?: string; done: number; total: number; file: string }

/**
 * The roster comes straight from the installed game: find the game, decompress
 * with Oodle, read the registry, index the assets. The page shows that chain, so
 * it's clear which link is missing; then any operator exports for Blender.
 */
export default function Operators({ go, setArt, status, refresh }: PageProps) {
  const { t } = useI18n()
  const { toast } = useSession()
  const [read, setRead] = useState<Read>({ state: 'waiting' })
  const [index, setIndex] = useState<Index | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [indexing, setIndexing] = useState(false)
  const [exporting, setExporting] = useState('')
  const [selected, setSelected] = useState('')
  const [query, setQuery] = useState('')
  const gameOk = !!status?.game.ok
  const oodleOk = !!status?.oodle.ok

  useEffect(() => setArt({ seed: 7, hue: 28 }), [])
  useEffect(() => {
    api.call<Index>('operators.status').then(setIndex).catch(() => undefined)
  }, [])
  useEffect(() => {
    if (!gameOk || !oodleOk) return setRead({ state: 'waiting' })
    setRead({ state: 'reading' })
    api
      .call<Operator[]>('operators.list')
      .then((operators) => setRead({ state: 'ok', operators }))
      .catch((e: Error) => setRead({ state: e.message.includes("isn't supported") ? 'outdated' : 'failed', error: e.message }))
  }, [gameOk, oodleOk])
  useEngineEvent<Progress>('operators.progress', setProgress)

  const pickOodle = async () => {
    const dll = await api.pick('file', ['dll'])
    if (!dll) return
    await api.call('settings.set', { oodle: dll })
    refresh()
  }
  const buildIndex = async () => {
    setIndexing(true)
    try {
      setIndex(await api.call<Index>('operators.index'))
      toast(t('op.indexDone'), 'ok')
    } catch (e) {
      toast(t((e as Error).message), 'bad')
    } finally {
      setIndexing(false)
      setProgress(null)
    }
  }
  const exportOperator = async (o: Operator) => {
    setExporting(o.uid)
    try {
      const { folder } = await api.call<{ folder: string }>('operators.export', { uid: o.uid })
      setRead((r) => ({ ...r, operators: r.operators?.map((x) => (x.uid === o.uid ? { ...x, exported: folder } : x)) }))
      toast(t('op.exportDone', { name: o.name }), 'ok')
    } catch (e) {
      toast(t((e as Error).message), 'bad')
    } finally {
      setExporting('')
      setProgress(null)
    }
  }
  const openBlender = (o: Operator) =>
    api
      .call('operators.blender', { folder: o.exported })
      .then(() => toast(t('op.blenderStarted', { name: o.name }), 'ok'))
      .catch((e: Error) => toast(t(e.message), 'bad'))

  const store = status?.game.path.includes('steamapps') ? 'Steam' : 'Ubisoft Connect'
  const indexOk = !!index?.indexed && !indexing
  const links = [
    { key: 'game', icon: FolderSearch, ok: gameOk, detail: gameOk ? store : t('pipe.missing') },
    { key: 'oodle', icon: Cpu, ok: oodleOk, detail: oodleOk ? (status?.oodle.bundled ? t('check.oodle.bundled') : 'oo2core') : t('pipe.missing') },
    {
      key: 'read',
      icon: Users,
      ok: read.state === 'ok',
      detail: read.state === 'ok' ? t('pipe.count', { n: read.operators!.length }) : t(`pipe.${read.state}`)
    },
    {
      key: 'index',
      icon: Database,
      ok: indexOk,
      busy: indexing,
      detail: indexing ? t('op.indexing', { done: progress?.done ?? 0, total: progress?.total ?? '…' }) : indexOk ? bytes(index!.bytes) : t('pipe.indexMissing')
    }
  ]
  const shown = (read.operators ?? []).filter((o) => o.name.toLowerCase().includes(query.toLowerCase()))
  const current = read.operators?.find((o) => o.uid === selected)

  return (
    <div className="stack">
      <PageHead
        eyebrow={t('operators.eyebrow')}
        title={t('operators.title')}
        sub={t('operators.sub')}
        right={
          read.state === 'ok' && (
            <label className="search">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('operators.search')} />
            </label>
          )
        }
      />

      <div className="pipeline">
        {links.map(({ key, icon: Icon, ok, detail, busy: linkBusy }, i) => {
          const busy = linkBusy || (key === 'read' && read.state === 'reading')
          const bad = !ok && !busy && (key !== 'read' || read.state === 'outdated' || read.state === 'failed') && key !== 'index'
          return (
            <div key={key} className={`link${ok ? ' ok' : bad ? ' bad' : ''}`}>
              <span className="link-icon">{busy ? <Spinner /> : <Icon size={18} strokeWidth={1.8} />}</span>
              <div className="grow">
                <small className="mono">0{i + 1}</small>
                <b>{t(`pipe.${key}`)}</b>
                <span>{detail}</span>
              </div>
              <span className="link-state">{ok ? <Check size={15} strokeWidth={3} /> : bad ? <X size={15} strokeWidth={3} /> : null}</span>
              {i < links.length - 1 && <ChevronRight className="link-arrow" size={18} />}
            </div>
          )
        })}
      </div>

      {!gameOk && status && (
        <div className="card explain">
          <b>{t('op.gameTitle')}</b>
          <p>{t('op.gameBody')}</p>
          <button className="btn primary small" onClick={() => go('settings')}>
            <FolderSearch size={14} /> {t('nav.settings')}
          </button>
        </div>
      )}
      {gameOk && !oodleOk && (
        <div className="card explain">
          <b>{t('op.oodleTitle')}</b>
          <p>{t('op.oodleBody')}</p>
          <button className="btn primary small" onClick={pickOodle}>
            <Cpu size={14} /> {t('op.pickOodle')}
          </button>
        </div>
      )}
      {(read.state === 'outdated' || read.state === 'failed') && (
        <div className="card explain">
          <b>{t(read.state === 'outdated' ? 'op.outdatedTitle' : 'op.failedTitle')}</b>
          <p>{t(read.state === 'outdated' ? 'op.outdatedBody' : 'op.failedBody')}</p>
          <details className="tech">
            <summary>{t('op.details')}</summary>
            <p className="mono">{read.error}</p>
          </details>
        </div>
      )}
      {read.state === 'ok' && index && !index.indexed && (
        <div className="card explain index-card">
          <b>{t('op.indexTitle')}</b>
          <p>{t('op.indexBody')}</p>
          {indexing ? (
            <div className="index-progress">
              <div className="bar">
                <i style={{ width: `${progress ? (progress.done / Math.max(progress.total, 1)) * 100 : 0}%` }} />
              </div>
              <small className="mono">{progress?.file || '…'}</small>
            </div>
          ) : (
            <button className="btn primary small" onClick={buildIndex}>
              <Database size={14} /> {t('op.buildIndex')}
            </button>
          )}
        </div>
      )}

      {read.state === 'ok' && (
        <div className={`ops-layout${current ? ' open' : ''}`}>
          <div className="grid ops">
            {shown.map((o, i) => (
              <button
                key={o.uid}
                className={`op${o.uid === selected ? ' on' : ''}`}
                style={{ '--i': Math.min(i, 16) } as React.CSSProperties}
                onClick={() => setSelected(o.uid === selected ? '' : o.uid)}
              >
                <div className="op-art">
                  <Shards seed={parseInt(o.uid.slice(-6), 16)} hue={hueOf(o.name)} />
                  <span>{o.name.slice(0, 2).toUpperCase()}</span>
                  {o.exported && (
                    <em className="op-done" aria-label={t('op.exported')}>
                      <Check size={12} strokeWidth={3} />
                    </em>
                  )}
                </div>
                <b>{o.name}</b>
                <small className="mono">{o.uid}</small>
              </button>
            ))}
          </div>

          {current && (
            <aside className="card op-panel" key={current.uid}>
              <button className="op-close" onClick={() => setSelected('')} aria-label={t('common.close')}>
                <X size={15} />
              </button>
              <div className="op-panel-art">
                <Shards seed={parseInt(current.uid.slice(-6), 16)} hue={hueOf(current.name)} />
                <span>{current.name.slice(0, 2).toUpperCase()}</span>
              </div>
              <b className="op-panel-name">{current.name}</b>
              <span className="op-panel-meta">
                <Box size={13} /> {t('op.models', { n: current.models })}
              </span>

              {exporting === current.uid ? (
                <div className="index-progress">
                  <div className="bar">
                    <i style={{ width: `${progress?.step === 'export' ? (progress.done / Math.max(progress.total, 1)) * 100 : 4}%` }} />
                  </div>
                  <small>{t('op.exporting', { part: t(`op.part.${progress?.file || 'body'}`) })}</small>
                </div>
              ) : current.exported ? (
                <div className="op-actions">
                  <button className="btn primary" onClick={() => openBlender(current)} disabled={!status?.blender.ok}>
                    <Box size={15} /> {t('op.openBlender')}
                  </button>
                  <div className="row">
                    <button className="btn ghost small" onClick={() => api.open(current.exported)}>
                      <FolderOpen size={14} /> {t('op.openFolder')}
                    </button>
                    <button className="btn ghost small" onClick={() => exportOperator(current)} disabled={!!exporting || indexing}>
                      <RefreshCw size={14} /> {t('op.reexport')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="op-actions">
                  <button className="btn primary" onClick={() => exportOperator(current)} disabled={!index?.indexed || !!exporting || indexing}>
                    <Download size={15} /> {t('op.export')}
                  </button>
                  {!index?.indexed && <small className="op-note">{t('op.needIndex')}</small>}
                </div>
              )}
              {!status?.blender.ok && <small className="op-note">{t('op.noBlender')}</small>}
              <small className="op-note mono">{index?.exports}</small>
            </aside>
          )}
        </div>
      )}
    </div>
  )
}
