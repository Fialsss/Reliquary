import { useEffect, useState } from 'react'
import { Check, ChevronRight, Cpu, FolderSearch, Search, Users, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, type Operator } from '../api'
import { hueOf, Shards } from '../art'
import { useI18n } from '../i18n'
import { PageHead, Spinner } from '../ui'

type Read = { state: 'waiting' | 'reading' | 'ok' | 'outdated' | 'failed'; operators?: Operator[]; error?: string }

/**
 * The roster comes straight from the installed game: find the game, decompress
 * with Oodle, read the registry. The page shows that chain, so it's clear which
 * link is missing.
 */
export default function Operators({ go, setArt, status, refresh }: PageProps) {
  const { t } = useI18n()
  const [read, setRead] = useState<Read>({ state: 'waiting' })
  const [query, setQuery] = useState('')
  const gameOk = !!status?.game.ok
  const oodleOk = !!status?.oodle.ok

  useEffect(() => setArt({ seed: 7, hue: 28 }), [])
  useEffect(() => {
    if (!gameOk || !oodleOk) return setRead({ state: 'waiting' })
    setRead({ state: 'reading' })
    api
      .call<Operator[]>('operators.list')
      .then((operators) => setRead({ state: 'ok', operators }))
      .catch((e: Error) => setRead({ state: e.message.includes("isn't supported") ? 'outdated' : 'failed', error: e.message }))
  }, [gameOk, oodleOk])

  const pickOodle = async () => {
    const dll = await api.pick('file', ['dll'])
    if (!dll) return
    await api.call('settings.set', { oodle: dll })
    refresh()
  }

  const store = status?.game.path.includes('steamapps') ? 'Steam' : 'Ubisoft Connect'
  const links = [
    { key: 'game', icon: FolderSearch, ok: gameOk, detail: gameOk ? store : t('pipe.missing') },
    { key: 'oodle', icon: Cpu, ok: oodleOk, detail: oodleOk ? (status?.oodle.bundled ? t('check.oodle.bundled') : 'oo2core') : t('pipe.missing') },
    {
      key: 'read',
      icon: Users,
      ok: read.state === 'ok',
      detail:
        read.state === 'ok' ? t('pipe.count', { n: read.operators!.length }) : t(`pipe.${read.state}`)
    }
  ]
  const shown = (read.operators ?? []).filter((o) => o.name.toLowerCase().includes(query.toLowerCase()))

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
        {links.map(({ key, icon: Icon, ok, detail }, i) => {
          const busy = key === 'read' && read.state === 'reading'
          const bad = !ok && !busy && (key !== 'read' || read.state === 'outdated' || read.state === 'failed')
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

      {read.state === 'ok' && (
        <div className="grid ops">
          {shown.map((o, i) => (
            <div key={o.uid} className="op" style={{ '--i': Math.min(i, 16) } as React.CSSProperties}>
              <div className="op-art">
                <Shards seed={parseInt(o.uid.slice(-6), 16)} hue={hueOf(o.name)} />
                <span>{o.name.slice(0, 2).toUpperCase()}</span>
              </div>
              <b>{o.name}</b>
              <small className="mono">{o.uid}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
