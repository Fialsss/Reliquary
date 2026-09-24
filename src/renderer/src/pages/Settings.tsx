import { useEffect, useState } from 'react'
import { ChevronRight, CircleHelp, Coffee, ExternalLink, FolderOpen, FolderPlus, FolderTree, HardDrive, Info, LogIn, LogOut, RotateCcw, UserRound, X } from 'lucide-react'
import type { PageProps } from '../App'
import { api, bytes, type Settings as Values } from '../api'
import { Mark } from '../art'
import { useI18n, type Lang } from '../i18n'
import { Avatar, useSession } from '../session'
import { ConfirmButton, PageHead, Segmented, Spinner } from '../ui'

const REPO = 'https://github.com/Fialsss/Reliquary'
const KOFI = 'https://ko-fi.com/fialss'
const VERSION = __VERSION__

const SECTIONS = [
  ['account', UserRound],
  ['paths', FolderTree],
  ['storage', HardDrive],
  ['help', CircleHelp],
  ['about', Info]
] as const
type Section = (typeof SECTIONS)[number][0]

type PathKey = 'game_dir' | 'blender' | 'oodle' | 'library' | 'exports'
const PATHS: { key: PathKey; kind: 'file' | 'folder'; ext?: string[]; detected?: 'game' | 'blender' | 'oodle' }[] = [
  { key: 'game_dir', kind: 'folder', detected: 'game' },
  { key: 'blender', kind: 'file', ext: ['exe'], detected: 'blender' },
  { key: 'oodle', kind: 'file', ext: ['dll'], detected: 'oodle' },
  { key: 'library', kind: 'folder' },
  { key: 'exports', kind: 'folder' }
]
const FAQ = ['smartscreen', 'owns', 'space', 'where', 'safe', 'oodle', 'next'] as const
const CREDITS = [
  ['R6-parser', 'TrueShadow01', 'https://github.com/TrueShadow01/R6-parser'],
  ['DepotDownloader', 'SteamRE', 'https://github.com/SteamRE/DepotDownloader'],
  ['ooz', 'powzix', 'https://github.com/powzix/ooz'],
  ['RainbowForge', 'parzivail', 'https://github.com/parzivail/RainbowForge']
] as const

export default function Settings({ status, refresh, setArt, startTour }: PageProps) {
  const { t, lang, setLang } = useI18n()
  const { profile, signIn, signOut } = useSession()
  const [values, setValues] = useState<Values | null>(null)
  const [section, setSection] = useState<Section>('account')

  useEffect(() => {
    setArt({ seed: 3, hue: 220 })
    api.call<Values>('settings.get').then(setValues)
  }, [])

  const save = async (changes: Partial<Values>) => {
    setValues(await api.call<Values>('settings.set', changes))
    refresh()
  }
  const browse = async (key: PathKey, kind: 'file' | 'folder', ext?: string[]) => {
    const picked = await api.pick(kind, ext)
    if (picked) save({ [key]: picked })
  }

  return (
    <div className="stack">
      <PageHead eyebrow={t('settings.eyebrow')} title={t('settings.title')} />
      <div className="settings">
        <nav className="settings-nav">
          {SECTIONS.map(([id, Icon]) => (
            <button key={id} className={section === id ? 'on' : ''} onClick={() => setSection(id)}>
              <Icon size={17} strokeWidth={1.8} />
              {t(`section.${id}`)}
            </button>
          ))}
        </nav>

        <section className="card settings-panel" key={section}>
          <header>
            <h2>{t(`section.${section}`)}</h2>
            <p>{t(`section.${section}.sub`)}</p>
          </header>

          {section === 'account' && (
            <>
              <div className="setting">
                <div className="setting-label">
                  <b>{t('setting.steam')}</b>
                  <small>{t('setting.steam.hint')}</small>
                </div>
                <div className="setting-control">
                  {profile ? (
                    <div className="profile-chip">
                      <Avatar profile={profile} size={36} />
                      <div className="grow">
                        <b>{profile.name}</b>
                        <small className="mono">{profile.steamid || `@${profile.user}`}</small>
                      </div>
                      <button className="btn ghost small danger" onClick={signOut}>
                        <LogOut size={14} /> {t('steam.signOut')}
                      </button>
                    </div>
                  ) : (
                    <button className="btn primary small" onClick={signIn}>
                      <LogIn size={14} /> {t('account.signIn')}
                    </button>
                  )}
                </div>
              </div>
              <div className="setting">
                <div className="setting-label">
                  <b>{t('setting.language')}</b>
                  <small>{t('setting.language.hint')}</small>
                </div>
                <div className="setting-control">
                  <Segmented<Lang> value={lang} onChange={setLang} options={[['it', 'Italiano'], ['en', 'English']]} />
                </div>
              </div>
            </>
          )}

          {section === 'paths' &&
            PATHS.map(({ key, kind, ext, detected }) => {
              const found = detected ? status?.[detected] : undefined
              const value = values?.[key] || ''
              const ok = detected ? !!found?.ok : true
              const shown = value || found?.path || ''
              return (
                <div key={key} className="setting">
                  <div className="setting-label">
                    <b>{t(`setting.${key}`)}</b>
                    <small>{t(`setting.${key}.hint`)}</small>
                  </div>
                  <div className="setting-control">
                    <div className={`path-field${ok ? ' ok' : ' missing'}`} data-tip={shown || undefined}>
                      <i />
                      <span className="mono">{shown || t('setting.notSet')}</span>
                      {detected && !value && found?.ok && <em>{t('setting.autoTag')}</em>}
                    </div>
                    {value && detected && (
                      <button className="btn ghost small icon" onClick={() => save({ [key]: '' })} data-tip={t('setting.reset')}>
                        <RotateCcw size={14} />
                      </button>
                    )}
                    <button className={`btn small ${ok ? 'ghost' : 'primary'}`} onClick={() => browse(key, kind, ext)}>
                      <FolderOpen size={14} /> {ok ? t('common.change') : t('common.browse')}
                    </button>
                  </div>
                </div>
              )
            })}
          {section === 'paths' && <OldBuilds list={values?.old_builds ?? []} save={save} />}

          {section === 'storage' && <Storage />}

          {section === 'help' && (
            <>
              <div className="setting">
                <div className="setting-label">
                  <b>{t('nav.guide')}</b>
                  <small>{t('help.tour.hint')}</small>
                </div>
                <div className="setting-control">
                  <button className="btn ghost small" onClick={startTour}>
                    <CircleHelp size={14} /> {t('help.tour')}
                  </button>
                </div>
              </div>
              <div className="faq">
                {FAQ.map((key) => (
                  <details key={key}>
                    <summary>
                      {t(`faq.${key}.q`)}
                      <ChevronRight size={15} />
                    </summary>
                    <p>{t(`faq.${key}.a`)}</p>
                  </details>
                ))}
              </div>
            </>
          )}

          {section === 'about' && (
            <>
              <div className="about-head">
                <Mark size={48} />
                <div className="grow">
                  <b>Reliquary</b>
                  <small className="mono">
                    v{VERSION} · GPL-3.0 · © 2026 Fialsss
                  </small>
                </div>
                <a className="btn primary small" href={KOFI} target="_blank" rel="noreferrer">
                  <Coffee size={14} /> {t('about.support')}
                </a>
                <a className="btn ghost small" href={REPO} target="_blank" rel="noreferrer">
                  <ExternalLink size={14} /> GitHub
                </a>
              </div>
              <div className="setting credit">
                <div className="setting-label">
                  <b>{t('about.author')}</b>
                  <small>{t('about.authorHint')}</small>
                </div>
                <div className="setting-control">
                  <a className="link-btn" href="https://github.com/Fialsss" target="_blank" rel="noreferrer">
                    Fialsss <ExternalLink size={12} />
                  </a>
                </div>
              </div>
              {CREDITS.map(([name, author, url]) => (
                <div key={name} className="setting credit">
                  <div className="setting-label">
                    <b>{name}</b>
                    <small>{t(`credit.${name}`, { author })}</small>
                  </div>
                  <div className="setting-control">
                    <a className="link-btn muted" href={url} target="_blank" rel="noreferrer">
                      github.com/{url.split('github.com/')[1]} <ExternalLink size={12} />
                    </a>
                  </div>
                </div>
              ))}
              <p className="fine-print">{t('about.body')}</p>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

/** Folders of old seasons (from the Vault or another launcher): retired skins like Glacier come from them. */
function OldBuilds({ list, save }: { list: string[]; save: (changes: Partial<Values>) => void }) {
  const { t } = useI18n()
  // the ones the engine can use (there, with their registry): the others get a red dot
  const [usable, setUsable] = useState<string[]>([])
  useEffect(() => {
    api.call<string[]>('retired.builds').then(setUsable).catch(() => setUsable([]))
  }, [list])
  const add = async () => {
    const picked = await api.pick('folder')
    if (picked && !list.includes(picked)) save({ old_builds: [...list, picked] })
  }
  return (
    <div className="setting">
      <div className="setting-label">
        <b>{t('setting.old_builds')}</b>
        <small>{t('setting.old_builds.hint')}</small>
      </div>
      <div className="setting-control old-builds">
        {list.map((path) => (
          <div key={path} className="old-build">
            <div className={`path-field${usable.includes(path) ? ' ok' : ' missing'}`} data-tip={usable.includes(path) ? path : t('setting.buildUnusable')}>
              <i />
              <span className="mono">{path}</span>
            </div>
            <button className="btn ghost small icon" onClick={() => save({ old_builds: list.filter((p) => p !== path) })} data-tip={t('setting.removeBuild')}>
              <X size={14} />
            </button>
          </div>
        ))}
        <button className={`btn small ${list.length ? 'ghost' : 'primary'}`} onClick={add}>
          <FolderPlus size={14} /> {t('setting.addBuild')}
        </button>
      </div>
    </div>
  )
}

type Library = {
  root: string
  total: number
  cache: number
  items: { season: string; name: string; manifest: string; date: string; bytes: number; files: number }[]
}

/** What the Vault keeps on disk, and the way to give the space back. */
function Storage() {
  const { t } = useI18n()
  const { toast } = useSession()
  const [lib, setLib] = useState<Library | null>(null)

  useEffect(() => {
    api.call<Library>('vault.library').then(setLib)
  }, [])

  const run = (method: string, params: Record<string, string>, done: string) =>
    api
      .call<Library>(method, params)
      .then((next) => {
        setLib(next)
        toast(done, 'ok')
      })
      .catch((e: Error) => toast(t(e.message), 'bad'))

  if (!lib) {
    return (
      <div className="center">
        <Spinner />
      </div>
    )
  }

  return (
    <>
      <div className="setting">
        <div className="setting-label">
          <b>{t('storage.library')}</b>
          <small>{t('storage.libraryHint')}</small>
        </div>
        <div className="setting-control">
          <span className="storage-total">{bytes(lib.total)}</span>
          <button className="btn ghost small" onClick={() => api.open(lib.root)}>
            <FolderOpen size={14} /> {t('vault.openFolder')}
          </button>
          {lib.items.length > 0 && (
            <ConfirmButton
              label={t('storage.deleteAll')}
              confirm={t('storage.confirm')}
              onConfirm={() => run('vault.delete', {}, t('storage.deleted', { size: bytes(lib.total) }))}
            />
          )}
        </div>
      </div>
      {lib.items.length === 0 ? (
        <p className="storage-empty">{t('storage.empty')}</p>
      ) : (
        <ul className="storage-list">
          {lib.items.map((item) => (
            <li key={item.manifest}>
              <span className="mono dim">{item.season}</span>
              <div className="grow">
                <b>{item.name}</b>
                <small className="mono">
                  {item.date} · {t('storage.files', { n: item.files })}
                </small>
              </div>
              <span className="storage-size">{bytes(item.bytes)}</span>
              <ConfirmButton
                label={t('storage.delete')}
                confirm={t('storage.confirm')}
                onConfirm={() => run('vault.delete', { season: item.season, manifest: item.manifest }, t('storage.deleted', { size: bytes(item.bytes) }))}
              />
            </li>
          ))}
        </ul>
      )}
      <div className="setting">
        <div className="setting-label">
          <b>{t('storage.cache')}</b>
          <small>{t('storage.cacheHint')}</small>
        </div>
        <div className="setting-control">
          <span className="storage-total">{bytes(lib.cache)}</span>
          <ConfirmButton label={t('storage.clear')} confirm={t('storage.confirm')} onConfirm={() => run('vault.clear_cache', {}, t('storage.cleared'))} />
        </div>
      </div>
    </>
  )
}
