import { useEffect, useState } from 'react'
import { AlertTriangle, RotateCw, Search, SlidersHorizontal } from 'lucide-react'
import type { PageProps } from '../App'
import { api, type Operator } from '../api'
import { hueOf, Shards } from '../art'
import { useI18n } from '../i18n'
import { PageHead, Spinner } from '../ui'

export default function Operators({ go, setArt }: PageProps) {
  const { t } = useI18n()
  const [operators, setOperators] = useState<Operator[] | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  const load = () => {
    setError('')
    setOperators(null)
    api.call<Operator[]>('operators.list').then(setOperators).catch((e: Error) => setError(e.message))
  }
  useEffect(() => {
    setArt({ seed: 7, hue: 28 })
    load()
  }, [])

  const shown = (operators ?? []).filter((o) => o.name.toLowerCase().includes(query.toLowerCase()))

  return (
    <div className="stack">
      <PageHead
        eyebrow={t('operators.eyebrow')}
        title={t('operators.title')}
        sub={t('operators.sub')}
        right={
          operators && (
            <label className="search">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('operators.search')} />
            </label>
          )
        }
      />
      {error ? (
        <div className="card empty">
          <span className="tile-icon warn">
            <AlertTriangle size={18} />
          </span>
          <b>{t('operators.unavailable')}</b>
          <p className="mono">{error}</p>
          <div className="row">
            <button className="btn primary" onClick={load}>
              <RotateCw size={15} /> {t('common.retry')}
            </button>
            <button className="btn ghost" onClick={() => go('settings')}>
              <SlidersHorizontal size={15} /> {t('nav.settings')}
            </button>
          </div>
        </div>
      ) : !operators ? (
        <div className="center">
          <Spinner size={22} />
          <span>{t('operators.reading')}</span>
        </div>
      ) : (
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
