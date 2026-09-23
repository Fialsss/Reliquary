import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Box, Check, ChevronRight, Cpu, Database, FolderOpen, FolderSearch, Package, Search, Users, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, bytes, useEngineEvent, type Operator } from '../api'
import { hueOf, Shards } from '../art'
import { useI18n } from '../i18n'
import { useSession } from '../session'
import { PageHead, Segmented, Spinner } from '../ui'

type Read = { state: 'waiting' | 'reading' | 'ok' | 'outdated' | 'failed'; operators?: Operator[]; error?: string }
type Index = { indexed: boolean; bytes: number; exports: string; busy: boolean }
type Progress = { step: 'index' | 'cache' | 'export' | 'blend' | 'done'; uid?: string; done: number; total: number; file: string }
type Cosmetic = { uid: string; kind: 'uniform' | 'headgear'; default: boolean; label: string }
type Cosmetics = { uniform: Cosmetic[]; headgear: Cosmetic[] }

/**
 * The roster comes straight from the installed game: find the game, decompress
 * with Oodle, read the registry, index the assets. The page shows that chain, so
 * it's clear which link is missing; then any operator becomes a Blender pack.
 */
export default function Operators({ go, setArt, status, refresh }: PageProps) {
  const { t } = useI18n()
  const { toast } = useSession()
  const [read, setRead] = useState<Read>({ state: 'waiting' })
  const [index, setIndex] = useState<Index | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [indexing, setIndexing] = useState(false)
  const [open, setOpen] = useState<Operator | null>(null)
  const [query, setQuery] = useState('')
  const gameOk = !!status?.game.ok
  const oodleOk = !!status?.oodle.ok

  useEffect(() => setArt({ seed: 7, hue: 28 }), [])
  useEffect(() => {
    api.call<Index>('operators.status').then(setIndex).catch(() => undefined)
  }, [])
  const load = () =>
    api
      .call<Operator[]>('operators.list')
      .then((operators) => setRead({ state: 'ok', operators }))
      .catch((e: Error) => setRead({ state: e.message.includes("isn't supported") ? 'outdated' : 'failed', error: e.message }))
  useEffect(() => {
    if (!gameOk || !oodleOk) return setRead({ state: 'waiting' })
    setRead({ state: 'reading' })
    load()
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

  if (open) {
    return (
      <OperatorPack
        operator={open}
        indexed={!!index?.indexed}
        blenderOk={!!status?.blender.ok}
        progress={progress?.uid === open.uid || progress?.step === 'cache' ? progress : null}
        back={() => {
          setOpen(null)
          setProgress(null)
          load()
        }}
      />
    )
  }

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
        <div className="grid ops">
          {shown.map((o, i) => (
            <button key={o.uid} className="op" style={{ '--i': Math.min(i, 16) } as React.CSSProperties} onClick={() => setOpen(o)}>
              <div className="op-art">
                <Shards seed={parseInt(o.uid.slice(-6), 16)} hue={hueOf(o.name)} />
                <span>{o.name.slice(0, 2).toUpperCase()}</span>
                {o.blend && (
                  <em className="op-done" aria-label={t('pack.ready')}>
                    <Check size={12} strokeWidth={3} />
                  </em>
                )}
              </div>
              <b>{o.name}</b>
              <small className="mono">{o.uid}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

type Weapon = { uid: string; name: string; model: string; code: string; skins: { id: string; name: string }[] }
type Charm = { id: string; name: string }
type Tab = 'uniform' | 'headgear' | 'weapon' | 'charm'

/**
 * One operator: pick uniforms and headgear from the game's own icons (Elite ones have the gold
 * background), weapon skins and charms from what the game has downloaded, then build a Blender pack:
 * every pick becomes a collection in one .blend.
 */
function OperatorPack({ operator, indexed, blenderOk, progress, back }: { operator: Operator; indexed: boolean; blenderOk: boolean; progress: Progress | null; back: () => void }) {
  const { t } = useI18n()
  const { toast } = useSession()
  const [items, setItems] = useState<Cosmetics | null>(null)
  const [weapons, setWeapons] = useState<Weapon[] | null>(null)
  const [charms, setCharms] = useState<Charm[] | null>(null)
  const [icons, setIcons] = useState<Record<string, string>>({})
  const [tab, setTab] = useState<Tab>('uniform')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [skins, setSkins] = useState<Record<string, Set<string>>>({})
  const [charmPicks, setCharmPicks] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [blend, setBlend] = useState(operator.blend)
  const [folder, setFolder] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .call<Cosmetics>('operators.cosmetics', { uid: operator.uid })
      .then((c) => {
        setItems(c)
        setPicked(new Set([...c.uniform, ...c.headgear].filter((i) => i.default).map((i) => i.uid)))
      })
      .catch((e: Error) => setError(e.message))
  }, [operator.uid])

  // weapons and charms read the game's download cache: only once someone opens their tab
  const cacheTab = tab === 'weapon' || tab === 'charm'
  useEffect(() => {
    if (!cacheTab || !indexed || weapons) return
    api.call<Weapon[]>('operators.weapons', { uid: operator.uid }).then(setWeapons).catch((e: Error) => setError(e.message))
    api.call<Charm[]>('dcache.charms').then(setCharms).catch(() => setCharms([]))
  }, [cacheTab, indexed])

  // pictures come in batches, the visible tab first; decoded once, then served from the app folder
  const visible = useMemo(() => {
    if (tab === 'weapon') return (weapons ?? []).flatMap((w) => w.skins.map((s) => s.id))
    if (tab === 'charm') return (charms ?? []).map((c) => c.id)
    return [...(items?.[tab] ?? []), ...(items?.[tab === 'uniform' ? 'headgear' : 'uniform'] ?? [])].map((i) => i.uid)
  }, [tab, items, weapons, charms])
  useEffect(() => {
    if (!indexed) return
    let alive = true
    const order = visible.filter((u) => !icons[u])
    const method = cacheTab ? 'operators.thumbs' : 'operators.icons'
    ;(async () => {
      for (let i = 0; i < order.length && alive; i += 24) {
        const args = cacheTab ? { ids: order.slice(i, i + 24) } : { uids: order.slice(i, i + 24) }
        const batch = await api.call<Record<string, string>>(method, args).catch(() => ({}))
        if (alive) setIcons((all) => ({ ...all, ...batch }))
      }
    })()
    return () => {
      alive = false
    }
  }, [visible, indexed])

  const toggle = (uid: string) => {
    const next = new Set(picked)
    next.has(uid) ? next.delete(uid) : next.add(uid)
    setPicked(next)
  }
  const toggleSkin = (weapon: string, id: string) => {
    const next = new Set(skins[weapon] ?? [])
    next.has(id) ? next.delete(id) : next.add(id)
    setSkins({ ...skins, [weapon]: next })
  }
  const toggleCharm = (id: string) => {
    const next = new Set(charmPicks)
    next.has(id) ? next.delete(id) : next.add(id)
    setCharmPicks(next)
  }
  const setAll = (on: boolean) => {
    if (tab === 'weapon') return setSkins(on ? Object.fromEntries((weapons ?? []).map((w) => [w.uid, new Set(['', ...w.skins.map((s) => s.id)])])) : {})
    if (tab === 'charm') return setCharmPicks(on ? new Set(shownCharms.map((c) => c.id)) : new Set())
    const next = new Set(picked)
    items?.[tab].forEach((i) => (on ? next.add(i.uid) : next.delete(i.uid)))
    setPicked(next)
  }
  const counts = {
    uniform: items?.uniform.filter((i) => picked.has(i.uid)).length ?? 0,
    headgear: items?.headgear.filter((i) => picked.has(i.uid)).length ?? 0,
    weapon: Object.values(skins).reduce((n, s) => n + s.size, 0),
    charm: charmPicks.size
  }
  const shownCharms = (charms ?? []).filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      const r = await api.call<{ folder: string; blend: string }>('operators.pack', {
        uid: operator.uid,
        items: [...picked],
        weapons: Object.entries(skins)
          .filter(([, s]) => s.size)
          .map(([uid, s]) => ({ uid, skins: [...s] })),
        charms: [...charmPicks]
      })
      setFolder(r.folder)
      setBlend(r.blend)
      toast(t('pack.done', { name: operator.name }), 'ok')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const openBlender = () => api.call('operators.blender', { path: blend }).catch((e: Error) => toast(t(e.message), 'bad'))
  const phase = progress?.step === 'blend' ? 'pack.blending' : progress?.step === 'cache' ? 'pack.cacheReading' : 'pack.exporting'
  const share = progress && progress.step !== 'done' ? (progress.done / Math.max(progress.total, 1)) * (progress.step === 'blend' ? 0.4 : 0.6) + (progress.step === 'blend' ? 0.6 : 0) : 0
  const count = { uniform: items?.uniform.length, headgear: items?.headgear.length, weapon: weapons?.reduce((n, w) => n + w.skins.length, 0), charm: charms?.length }
  const card = (id: string, on: boolean, onClick: () => void, caption?: string, tag?: string) => (
    <button key={id || 'none'} className={`cosmetic${on ? ' on' : ''}${caption ? ' captioned' : ''}`} onClick={onClick} disabled={busy} title={caption}>
      {id && icons[id] ? <img src={icons[id]} alt="" draggable={false} /> : id ? <span className="cosmetic-wait" /> : <span className="cosmetic-none" />}
      {on && (
        <em className="cosmetic-check">
          <Check size={12} strokeWidth={3} />
        </em>
      )}
      {tag && <span className="cosmetic-tag">{tag}</span>}
      {caption && <span className="cosmetic-caption">{caption}</span>}
    </button>
  )

  return (
    <div className="detail">
      <aside className="detail-side">
        <button className="back" onClick={back}>
          <ArrowLeft size={15} /> {t('pack.back')}
        </button>
        <div className="detail-cover">
          <Shards seed={parseInt(operator.uid.slice(-6), 16)} hue={hueOf(operator.name)} />
          <div className="detail-cover-text">
            <span className="mono">{operator.uid}</span>
            <b>{operator.name}</b>
          </div>
        </div>
        <div className="card pack-summary">
          <div className="label">{t('pack.title')}</div>
          <p>{t('pack.hint')}</p>
          <div className="pack-counts">
            {(['uniform', 'headgear', 'weapon', 'charm'] as const).map((k) => (
              <span key={k}>
                <b>{counts[k]}</b> {t(`pack.${k}s`)}
              </span>
            ))}
          </div>
          {busy ? (
            <div className="index-progress">
              <div className="bar">
                <i style={{ width: `${Math.max(3, share * 100)}%` }} />
              </div>
              <small>{progress ? t(phase, { done: progress.done, total: progress.total }) : '…'}</small>
            </div>
          ) : (
            <button className="btn primary" onClick={create} disabled={!indexed || !counts.uniform || !counts.headgear}>
              <Package size={16} /> {t('pack.create')}
            </button>
          )}
          {!indexed && <small className="op-note">{t('op.needIndex')}</small>}
          {indexed && !blenderOk && <small className="op-note">{t('pack.noBlender')}</small>}
          {!busy && (blend || folder) && (
            <div className="row pack-open">
              {blend && (
                <button className="btn ghost small" onClick={openBlender}>
                  <Box size={14} /> {t('op.openBlender')}
                </button>
              )}
              <button className="btn ghost small" onClick={() => api.open(folder || blend.replace(/[\\/][^\\/]+$/, ''))}>
                <FolderOpen size={14} /> {t('op.openFolder')}
              </button>
            </div>
          )}
        </div>
      </aside>

      <section className="detail-main">
        {error && (
          <div className="notice">
            <span>{t(error)}</span>
          </div>
        )}
        <div className="card cosmetics">
          <div className="cosmetics-head">
            <Segmented
              value={tab}
              onChange={(v) => setTab(v as Tab)}
              options={(['uniform', 'headgear', 'weapon', 'charm'] as const).map((k): [string, string] => [k, `${t(`pack.${k}s`)} · ${count[k] ?? '…'}`])}
            />
            <div className="row">
              {tab === 'charm' && (
                <label className="search small">
                  <Search size={14} />
                  <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('pack.searchCharms')} />
                </label>
              )}
              <button className="btn ghost small" onClick={() => setAll(true)} disabled={busy}>
                {t('pack.all')}
              </button>
              <button className="btn ghost small" onClick={() => setAll(false)} disabled={busy}>
                {t('pack.none')}
              </button>
            </div>
          </div>
          {cacheTab && <small className="cache-hint">{t('pack.cacheHint')}</small>}

          {(tab === 'uniform' || tab === 'headgear') &&
            (!items ? (
              <div className="center">
                <Spinner size={22} />
              </div>
            ) : (
              <div className="cosmetic-grid" key={tab}>
                {items[tab].map((item) => card(item.uid, picked.has(item.uid), () => toggle(item.uid), undefined, item.default ? t('pack.default') : undefined))}
              </div>
            ))}

          {tab === 'weapon' &&
            (!weapons ? (
              <div className="center column">
                <Spinner size={22} />
                {progress?.step === 'cache' && <small>{t('pack.cacheReading', { done: progress.done, total: progress.total })}</small>}
              </div>
            ) : (
              <div className="cosmetic-grid scroll-sections">
                {weapons.map((w, n) => (
                  <section key={w.uid} className="weapon-block">
                    <header>
                      <b>{w.name || w.code || t('pack.weaponUnknown', { n: n + 1 })}</b>
                      <small>{w.skins.length ? t('pack.skinsCount', { n: w.skins.length }) : t('pack.noSkins')}</small>
                    </header>
                    <div className="skin-grid">
                      {card('', skins[w.uid]?.has('') ?? false, () => toggleSkin(w.uid, ''), t('pack.noSkin'))}
                      {w.skins.map((s) => card(s.id, skins[w.uid]?.has(s.id) ?? false, () => toggleSkin(w.uid, s.id), s.name))}
                    </div>
                  </section>
                ))}
              </div>
            ))}

          {tab === 'charm' &&
            (!charms ? (
              <div className="center">
                <Spinner size={22} />
              </div>
            ) : (
              <div className="cosmetic-grid">{shownCharms.map((c) => card(c.id, charmPicks.has(c.id), () => toggleCharm(c.id), c.name))}</div>
            ))}
        </div>
      </section>
    </div>
  )
}
