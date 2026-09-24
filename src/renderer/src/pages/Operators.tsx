import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Box, Check, ChevronDown, ChevronRight, CloudDownload, Cpu, Crosshair, Database, Focus, FolderOpen, FolderSearch, Gem, HardHat, Package, Search, Shirt, Users, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, bytes, useEngineEvent, type Operator } from '../api'
import { hueOf, Shards } from '../art'
import { useI18n } from '../i18n'
import { useSession } from '../session'
import { PageHead, Segmented, Spinner } from '../ui'

type Read = { state: 'waiting' | 'reading' | 'ok' | 'outdated' | 'failed'; operators?: Operator[]; error?: string }
type Index = { indexed: boolean; bytes: number; exports: string; busy: boolean }
type Progress = { step: 'index' | 'cache' | 'export' | 'blend' | 'done'; uid?: string; done: number; total: number; file: string }
type Cosmetic = { uid: string; kind: 'uniform' | 'headgear'; default: boolean; label: string; season: string; rarity: string }
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
  const [side, setSide] = useState<Side>('all')
  const [portraits, setPortraits] = useState<Record<string, string>>({})
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

  // the game's own portraits, once the roster and the index are there
  const indexed = !!index?.indexed
  useEffect(() => {
    const order = (read.operators ?? []).flatMap((o) => [o.uid, `${o.uid}.emblem`]).filter((u) => !(u in portraits))
    if (!indexed || !order.length) return
    let alive = true
    ;(async () => {
      for (let i = 0; i < order.length && alive; i += 24) {
        const part = order.slice(i, i + 24)
        const batch = await api.call<Record<string, string>>('operators.icons', { uids: part }).catch(() => ({}) as Record<string, string>)
        if (alive) setPortraits((all) => ({ ...all, ...Object.fromEntries(part.map((u) => [u, batch[u] ?? ''])) }))
      }
    })()
    return () => {
      alive = false
    }
  }, [read.operators, indexed])

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
        portrait={portraits[open.uid]}
        emblem={portraits[`${open.uid}.emblem`]}
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
  const all = read.operators ?? []
  const shown = all.filter((o) => o.name.toLowerCase().includes(query.toLowerCase()))
  const sides = (['attack', 'defense'] as const).filter((s) => side === 'all' || side === s)
  const sideCount = (s: Side) => all.filter((o) => s === 'all' || o.side === s).length
  // the game's card: portrait, the operator's emblem, the name in capitals
  const opCard = (o: Operator, i: number) => (
    <button key={o.uid} className={`op ${o.side}`} style={{ '--i': Math.min(i, 16) } as React.CSSProperties} onClick={() => setOpen(o)}>
      <span className="op-pic">
        {portraits[o.uid] ? <img src={portraits[o.uid]} alt="" draggable={false} /> : <span className="op-initials">{o.name.slice(0, 2).toUpperCase()}</span>}
      </span>
      {portraits[`${o.uid}.emblem`] && <img className="op-emblem" src={portraits[`${o.uid}.emblem`]} alt="" draggable={false} />}
      {o.blend && (
        <em className="op-done" aria-label={t('pack.ready')}>
          <Check size={12} strokeWidth={3} />
        </em>
      )}
      <span className="op-name">{o.name}</span>
    </button>
  )

  return (
    <div className="stack">
      <PageHead
        eyebrow={t('operators.eyebrow')}
        title={t('operators.title')}
        sub={t('operators.sub')}
        right={
          read.state === 'ok' && (
            <div className="row op-filters">
              <Segmented
                value={side}
                onChange={setSide}
                options={(['all', 'attack', 'defense'] as const).map((s): [Side, string] => [s, `${t(`side.${s}`)} · ${sideCount(s)}`])}
              />
              <label className="search">
                <Search size={15} />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('operators.search')} />
              </label>
            </div>
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

      {read.state === 'ok' &&
        sides.map((s) => {
          const list = shown.filter((o) => o.side === s)
          return (
            list.length > 0 && (
              <section key={s} className="op-section">
                <h2 className={`op-side ${s}`}>
                  {t(s === 'attack' ? 'side.attackers' : 'side.defenders')} <small>{list.length}</small>
                </h2>
                <div className="grid ops">
                  {list.map((o, i) => opCard(o, i))}
                </div>
              </section>
            )
          )
        })}
      {read.state === 'ok' && shown.some((o) => !o.side) && <div className="grid ops">{shown.filter((o) => !o.side).map(opCard)}</div>}
    </div>
  )
}

type Side = 'all' | 'attack' | 'defense'

type Skin = { id: string; icon: string; name: string; season: string; rarity: string; universal: boolean; file: string }
type Sight = { uid: string; name: string; model: string }
type Weapon = { uid: string; name: string; model: string; magazine: string; code: string; skins: Skin[]; sights: Sight[] }
type Charm = { id: string; icon: string; name: string; season: string; rarity: string; family: string; rank: string; file: string }
type Tab = 'uniform' | 'headgear' | 'weapon' | 'sight' | 'charm'

const TABS: Tab[] = ['uniform', 'headgear', 'weapon', 'sight', 'charm']
const TAB_ICONS = { uniform: Shirt, headgear: HardHat, weapon: Crosshair, sight: Focus, charm: Gem }
const FAMILIES = ['ranked', 'battlepass', 'esports', 'chibi', 'event', 'other']
const RANKS = ['copper', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'champion']
const yearOf = (season: string) => (season ? season.replace(/S\d$/, '') : 'none')
const seasonOrder = (code: string) => {
  const m = /^Y(\d+)(?:S(\d))?$/.exec(code)
  return m ? Number(m[1]) * 10 + Number(m[2] ?? 0) : -1
}

/** A dropdown of checkboxes: nothing ticked shows everything, each tick narrows to what's ticked. */
function Picker({ label, clear, options, picked, onChange }: { label: string; clear: string; options: [string, string, number][]; picked: Set<string>; onChange: (next: Set<string>) => void }) {
  const box = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const close = (e: PointerEvent) => box.current && !box.current.contains(e.target as Node) && (box.current.open = false)
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  const flip = (id: string) => {
    const next = new Set(picked)
    next.has(id) ? next.delete(id) : next.add(id)
    onChange(next)
  }
  return (
    <details className="picker" ref={box}>
      <summary className="btn ghost small">
        {label}
        {picked.size > 0 && <span className="picker-count">{picked.size}</span>}
        <ChevronDown size={14} />
      </summary>
      <div className="picker-menu">
        {options.map(([id, text, n]) => (
          <button key={id} className="picker-item" onClick={() => flip(id)}>
            <span className={`check${picked.has(id) ? ' on' : ''}`}>{picked.has(id) && <Check size={12} strokeWidth={3} />}</span>
            <span className="grow">{text}</span>
            <span className="mono">{n}</span>
          </button>
        ))}
        {picked.size > 0 && (
          <button className="picker-clear" onClick={() => onChange(new Set())}>
            {clear}
          </button>
        )}
      </div>
    </details>
  )
}

/**
 * One operator: pick uniforms, headgear, weapon skins, sights and charms, then build a Blender pack: every
 * pick becomes a collection in one .blend. Everything shows the game's own pictures; skins and charms come
 * from the game's whole catalog, and the ones it hasn't downloaded yet are marked (they can't be exported).
 */
function OperatorPack({
  operator,
  portrait,
  emblem,
  indexed,
  blenderOk,
  progress,
  back
}: {
  operator: Operator
  portrait?: string
  emblem?: string
  indexed: boolean
  blenderOk: boolean
  progress: Progress | null
  back: () => void
}) {
  const { t } = useI18n()
  const { toast } = useSession()
  const [items, setItems] = useState<Cosmetics | null>(null)
  const [weapons, setWeapons] = useState<Weapon[] | null>(null)
  const [charms, setCharms] = useState<Charm[] | null>(null)
  const [pics, setPics] = useState<Record<string, string>>({})
  const [tab, setTab] = useState<Tab>('uniform')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [skins, setSkins] = useState<Record<string, Set<string>>>({})
  const [sights, setSights] = useState<Record<string, Set<string>>>({})
  const [charmPicks, setCharmPicks] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [years, setYears] = useState<Set<string>>(new Set())
  const [families, setFamilies] = useState<Set<string>>(new Set())
  const [ranks, setRanks] = useState<Set<string>>(new Set())
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

  // weapons, sights and charms: only once someone opens their tab
  const catalogTab = tab === 'weapon' || tab === 'sight' || tab === 'charm'
  useEffect(() => {
    if (!catalogTab || !indexed || weapons) return
    api.call<Weapon[]>('operators.weapons', { uid: operator.uid }).then(setWeapons).catch((e: Error) => setError(e.message))
    api.call<Charm[]>('catalog.charms').then(setCharms).catch(() => setCharms([]))
  }, [catalogTab, indexed])

  // what the filters let through: search, seasons (skins and charms), kind and rank (charms)
  const q = query.toLowerCase()
  const inSeasons = (season: string) => !years.size || years.has(yearOf(season))
  const shownSkins = (w: Weapon) => w.skins.filter((s) => s.name.toLowerCase().includes(q) && inSeasons(s.season))
  const shownCharms = (charms ?? []).filter(
    (c) => c.name.toLowerCase().includes(q) && inSeasons(c.season) && (!families.size || families.has(c.family)) && (!ranks.size || ranks.has(c.rank))
  )

  const bySeason = useMemo(() => {
    const by = new Map<string, Charm[]>()
    shownCharms.forEach((c) => by.set(c.season, [...(by.get(c.season) ?? []), c]))
    for (const list of by.values()) list.sort((a, b) => RANKS.indexOf(a.rank) - RANKS.indexOf(b.rank) || a.name.localeCompare(b.name))
    return [...by.entries()].sort((a, b) => seasonOrder(b[0]) - seasonOrder(a[0]))
  }, [charms, query, years, families, ranks])
  const newestFirst = (a: Skin, b: Skin) => seasonOrder(b.season) - seasonOrder(a.season) || a.name.localeCompare(b.name)
  // a weapon's skins as the page lists them: universal first, then its own, each newest first
  const skinGroups = (w: Weapon): [string, Skin[]][] => {
    const shown = shownSkins(w)
    return [
      ['pack.universal', shown.filter((s) => s.universal).sort(newestFirst)],
      ['pack.exclusive', shown.filter((s) => !s.universal).sort(newestFirst)]
    ]
  }

  // the game's pictures of what's on screen, in the page's order and in batches; decoded once, then served from disk
  const wanted = useMemo((): string[] => {
    if (tab === 'uniform' || tab === 'headgear') return (items?.[tab] ?? []).map((i) => i.uid)
    if (tab === 'sight') return (weapons ?? []).flatMap((w) => w.sights.map((s) => s.uid))
    if (tab === 'charm') return bySeason.flatMap(([, list]) => list.map((c) => c.icon)).filter(Boolean)
    return (weapons ?? []).flatMap((w) => skinGroups(w).flatMap(([, list]) => list.map((s) => s.icon))).filter(Boolean)
  }, [tab, items, weapons, bySeason, query, years])
  useEffect(() => {
    if (!indexed) return
    let alive = true
    const order = [...new Set(wanted)].filter((u) => !(u in pics))
    ;(async () => {
      for (let i = 0; i < order.length && alive; i += 32) {
        const part = order.slice(i, i + 32)
        const got = await api.call<Record<string, string>>('operators.icons', { uids: part }).catch(() => ({}) as Record<string, string>)
        if (alive) setPics((all) => ({ ...all, ...Object.fromEntries(part.map((u) => [u, got[u] ?? ''])) }))
      }
    })()
    return () => {
      alive = false
    }
  }, [wanted, indexed])

  const flip = (set: Set<string>, id: string) => {
    const next = new Set(set)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  }
  const seasonsHere = tab === 'charm' ? (charms ?? []).map((c) => c.season) : (weapons ?? []).flatMap((w) => w.skins.map((s) => s.season))
  const yearOptions = [...new Set(seasonsHere.map(yearOf))]
    .sort((a, b) => (a === 'none' ? 1 : b === 'none' ? -1 : Number(b.slice(1)) - Number(a.slice(1))))
    .map((y): [string, string, number] => [y, y === 'none' ? t('pack.noSeason') : t('pack.year', { y: y.slice(1) }), seasonsHere.filter((s) => yearOf(s) === y).length])
  const familyOptions = FAMILIES.map((k): [string, string, number] => [k, t(`pack.family.${k}`), (charms ?? []).filter((c) => c.family === k).length])
  const rankOptions = RANKS.map((k): [string, string, number] => [k, t(`rank.${k}`), (charms ?? []).filter((c) => c.rank === k).length])
  // "select all" takes what can be exported: the items the game has downloaded
  const setAll = (on: boolean) => {
    if (tab === 'weapon') return setSkins(on ? Object.fromEntries((weapons ?? []).map((w) => [w.uid, new Set(['', ...shownSkins(w).filter((s) => s.file).map((s) => s.id)])])) : {})
    if (tab === 'sight') return setSights(on ? Object.fromEntries((weapons ?? []).map((w) => [w.uid, new Set(w.sights.map((s) => s.uid))])) : {})
    if (tab === 'charm') return setCharmPicks(on ? new Set(shownCharms.filter((c) => c.file).map((c) => c.id)) : new Set())
    const next = new Set(picked)
    items?.[tab].forEach((i) => (on ? next.add(i.uid) : next.delete(i.uid)))
    setPicked(next)
  }
  const sum = (picks: Record<string, Set<string>>) => Object.values(picks).reduce((n, s) => n + s.size, 0)
  const counts: Record<Tab, number> = {
    uniform: items?.uniform.filter((i) => picked.has(i.uid)).length ?? 0,
    headgear: items?.headgear.filter((i) => picked.has(i.uid)).length ?? 0,
    weapon: sum(skins),
    sight: sum(sights),
    charm: charmPicks.size
  }
  const total: Record<Tab, number | undefined> = {
    uniform: items?.uniform.length,
    headgear: items?.headgear.length,
    weapon: weapons?.reduce((n, w) => n + w.skins.length, 0),
    sight: weapons?.reduce((n, w) => n + w.sights.length, 0),
    charm: charms?.length
  }

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      const r = await api.call<{ folder: string; blend: string; skipped: number }>('operators.pack', {
        uid: operator.uid,
        items: [...picked],
        weapons: (weapons ?? [])
          .map((w) => ({ uid: w.uid, skins: [...(skins[w.uid] ?? [])], sights: [...(sights[w.uid] ?? [])] }))
          .filter((w) => w.skins.length || w.sights.length),
        charms: [...charmPicks]
      })
      setFolder(r.folder)
      setBlend(r.blend)
      toast(t('pack.done', { name: operator.name }), 'ok')
      if (r.skipped) toast(t('pack.skipped', { n: r.skipped }), 'muted')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const openBlender = () => api.call('operators.blender', { path: blend }).catch((e: Error) => toast(t(e.message), 'bad'))
  const phase = progress?.step === 'blend' ? 'pack.blending' : progress?.step === 'cache' ? 'pack.cacheReading' : 'pack.exporting'
  const share = progress && progress.step !== 'done' ? (progress.done / Math.max(progress.total, 1)) * (progress.step === 'blend' ? 0.4 : 0.6) + (progress.step === 'blend' ? 0.6 : 0) : 0

  /** A pickable card: the game's picture (a shimmer while it's decoded), a check when picked, the name under it.
   * Items the game hasn't downloaded yet can't be picked: they say how to get them. */
  const card = (
    key: string,
    pic: string,
    on: boolean,
    onClick: () => void,
    opts: { caption?: string; sub?: string; tag?: string; rarity?: string; shape: 'icon' | 'skin' | 'wide' | 'square'; missing?: boolean }
  ) => (
    <button
      key={key}
      className={`cosmetic ${opts.shape}${on ? ' on' : ''}${opts.missing ? ' missing' : ''}`}
      data-rarity={opts.rarity || undefined}
      onClick={opts.missing ? () => toast(t('pack.notDownloaded'), 'muted') : onClick}
      disabled={busy}
      title={opts.missing ? t('pack.notDownloaded') : opts.caption}
    >
      <span className="pic">{pic && pics[pic] ? <img src={pics[pic]} alt="" draggable={false} /> : !pic || pic in pics ? <span className="cosmetic-none" /> : <span className="cosmetic-wait" />}</span>
      {opts.caption && <span className="cosmetic-caption">{opts.caption}</span>}
      {opts.sub && <span className="cosmetic-sub">{opts.sub}</span>}
      {on && (
        <em className="cosmetic-check">
          <Check size={12} strokeWidth={3} />
        </em>
      )}
      {opts.tag && <span className="cosmetic-tag">{opts.tag}</span>}
      {opts.missing && (
        <span className="cosmetic-cloud">
          <CloudDownload size={13} /> {t('pack.toDownload')}
        </span>
      )}
    </button>
  )
  const weaponTitle = (w: Weapon, n: number) => w.name || w.code || t('pack.weaponUnknown', { n: n + 1 })
  const seasonLabel = (code: string) =>
    code.includes('S') ? t('pack.season', { y: code.slice(1, code.indexOf('S')), s: code.slice(code.indexOf('S') + 1) }) : t('pack.year', { y: code.slice(1) })
  const loading = (
    <div className="center column">
      <Spinner size={22} />
      {progress?.step === 'cache' && <small>{t('pack.cacheReading', { done: progress.done, total: progress.total })}</small>}
    </div>
  )

  return (
    <div className="detail">
      <aside className="detail-side">
        <button className="back" onClick={back}>
          <ArrowLeft size={15} /> {t('pack.back')}
        </button>
        <div className={`detail-cover op-cover ${operator.side}`}>
          {portrait ? <img src={portrait} alt="" draggable={false} /> : <Shards seed={parseInt(operator.uid.slice(-6), 16)} hue={hueOf(operator.name)} />}
          <div className="detail-cover-text">
            {emblem && <img className="op-emblem" src={emblem} alt="" draggable={false} />}
            <span>{t(`side.${operator.side || 'all'}`)}</span>
            <b>{operator.name}</b>
          </div>
        </div>
        <div className="card pack-summary">
          <div className="label">{t('pack.title')}</div>
          <p>{t('pack.hint')}</p>
          {/* what's in the pack so far; a row opens its tab */}
          <div className="pack-counts">
            {TABS.map((k) => {
              const Icon = TAB_ICONS[k]
              return (
                <button key={k} className={`pack-count${tab === k ? ' on' : ''}${counts[k] ? ' has' : ''}`} onClick={() => setTab(k)}>
                  <Icon size={16} strokeWidth={1.8} />
                  <span>{t(`pack.${k}s`)}</span>
                  <b>{counts[k]}</b>
                </button>
              )
            })}
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
            <Segmented value={tab} onChange={setTab} options={TABS.map((k): [Tab, string] => [k, `${t(`pack.${k}s`)} · ${total[k] ?? '…'}`])} />
            <div className="row">
              {(tab === 'weapon' || tab === 'charm') && (
                <label className="search small">
                  <Search size={14} />
                  <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t(tab === 'charm' ? 'pack.searchCharms' : 'pack.searchSkins')} />
                </label>
              )}
              {((tab === 'weapon' && weapons) || (tab === 'charm' && charms)) && (
                <Picker label={t('pack.seasons')} clear={t('pack.none')} options={yearOptions} picked={years} onChange={setYears} />
              )}
              {tab === 'charm' && charms && (
                <>
                  <Picker label={t('pack.kinds')} clear={t('pack.none')} options={familyOptions} picked={families} onChange={setFamilies} />
                  <Picker label={t('pack.ranks')} clear={t('pack.none')} options={rankOptions} picked={ranks} onChange={setRanks} />
                </>
              )}
              <button className="btn ghost small" onClick={() => setAll(true)} disabled={busy}>
                {t('pack.all')}
              </button>
              <button className="btn ghost small" onClick={() => setAll(false)} disabled={busy}>
                {t('pack.none')}
              </button>
            </div>
          </div>
          {(tab === 'weapon' || tab === 'charm') && <small className="cache-hint">{t('pack.cacheHint')}</small>}

          {(tab === 'uniform' || tab === 'headgear') &&
            (!items ? (
              loading
            ) : (
              <div className="cosmetic-grid" key={tab}>
                {items[tab].map((item) =>
                  card(item.uid, item.uid, picked.has(item.uid), () => setPicked(flip(picked, item.uid)), {
                    shape: 'icon',
                    caption: item.label || undefined,
                    sub: item.season || undefined,
                    rarity: item.rarity,
                    tag: item.default ? t('pack.default') : undefined
                  })
                )}
              </div>
            ))}

          {tab === 'weapon' &&
            (!weapons ? (
              loading
            ) : (
              <div className="cosmetic-grid scroll-sections" key={tab}>
                {weapons.map((w, n) => {
                  const on = skins[w.uid] ?? new Set<string>()
                  const pick = (id: string) => setSkins({ ...skins, [w.uid]: flip(on, id) })
                  const skinCard = (s: Skin) =>
                    card(s.id, s.icon, on.has(s.id), () => pick(s.id), { caption: s.name, sub: s.season, rarity: s.rarity, shape: 'skin', missing: !s.file })
                  const groups = skinGroups(w)
                  return (
                    <section key={w.uid} className="weapon-block">
                      <header>
                        <b>{weaponTitle(w, n)}</b>
                        <small>{w.skins.length ? t('pack.skinsCount', { n: w.skins.length, ready: w.skins.filter((s) => s.file).length }) : t('pack.noSkins')}</small>
                      </header>
                      <div className="skin-grid">{card(`${w.uid}:base`, '', on.has(''), () => pick(''), { caption: t('pack.noSkin'), shape: 'skin' })}</div>
                      {groups.map(
                        ([label, list]) =>
                          list.length > 0 && (
                            <div key={label} className="pack-group">
                              <h3 className="group-head">
                                {t(label)} <small>{list.length}</small>
                              </h3>
                              <div className="skin-grid">{list.map(skinCard)}</div>
                            </div>
                          )
                      )}
                    </section>
                  )
                })}
              </div>
            ))}

          {tab === 'sight' &&
            (!weapons ? (
              loading
            ) : (
              <div className="cosmetic-grid scroll-sections" key={tab}>
                {weapons
                  .filter((w) => w.sights.length)
                  .map((w, n) => {
                    const on = sights[w.uid] ?? new Set<string>()
                    return (
                      <section key={w.uid} className="weapon-block">
                        <header>
                          <b>{weaponTitle(w, n)}</b>
                          <small>{w.sights.length}</small>
                        </header>
                        <div className="skin-grid">
                          {w.sights.map((s, i) =>
                            card(s.uid, s.uid, on.has(s.uid), () => setSights({ ...sights, [w.uid]: flip(on, s.uid) }), {
                              caption: s.name || `${t('pack.sights')} ${i + 1}`,
                              shape: 'wide'
                            })
                          )}
                        </div>
                      </section>
                    )
                  })}
                {!weapons.some((w) => w.sights.length) && <p className="cosmetic-empty">{t('pack.noSights')}</p>}
              </div>
            ))}

          {tab === 'charm' &&
            (!charms ? (
              loading
            ) : (
              <div className="cosmetic-grid scroll-sections" key={tab}>
                {bySeason.map(([code, list]) => (
                  <section key={code || 'other'} className="pack-group">
                    <h3 className="group-head">
                      {code ? (
                        <>
                          <span className="season-code">{code}</span> {seasonLabel(code)}
                        </>
                      ) : (
                        t('pack.otherSeason')
                      )}{' '}
                      <small>{list.length}</small>
                    </h3>
                    <div className="charm-grid">
                      {list.map((c) =>
                        card(c.id, c.icon, charmPicks.has(c.id), () => setCharmPicks(flip(charmPicks, c.id)), {
                          caption: c.name,
                          sub: c.rank ? t(`rank.${c.rank}`) : undefined,
                          rarity: c.rarity,
                          shape: 'square',
                          missing: !c.file
                        })
                      )}
                    </div>
                  </section>
                ))}
              </div>
            ))}
        </div>
      </section>
    </div>
  )
}
