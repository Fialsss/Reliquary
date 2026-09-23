import { useEffect, useState } from 'react'
import { ExternalLink, FolderOpen, LogOut } from 'lucide-react'
import type { PageProps } from '../App'
import { api, type Settings as Values } from '../api'
import { useI18n, type Lang } from '../i18n'
import { Chip, PageHead, Segmented } from '../ui'

const REPO = 'https://github.com/Fialsss/Reliquary'

type PathKey = 'game_dir' | 'blender' | 'oodle' | 'library'
const PATHS: { key: PathKey; kind: 'file' | 'folder'; ext?: string[]; detected?: 'game' | 'blender' | 'oodle' }[] = [
  { key: 'game_dir', kind: 'folder', detected: 'game' },
  { key: 'oodle', kind: 'file', ext: ['dll'], detected: 'oodle' },
  { key: 'blender', kind: 'file', ext: ['exe'], detected: 'blender' },
  { key: 'library', kind: 'folder' }
]

export default function Settings({ status, refresh, setArt }: PageProps) {
  const { t, lang, setLang } = useI18n()
  const [values, setValues] = useState<Values | null>(null)

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
    <div className="stack narrow">
      <PageHead eyebrow={t('settings.eyebrow')} title={t('settings.title')} />
      <div className="card options">
        {PATHS.map(({ key, kind, ext, detected }) => {
          const found = detected ? status?.[detected] : undefined
          const value = values?.[key] || ''
          return (
            <div key={key} className="option">
              <div className="grow">
                <b>{t(`setting.${key}`)}</b>
                <small>{t(`setting.${key}.hint`)}</small>
                <span className="mono path">{value || (found?.path ? t('setting.auto', { path: found.path }) : t('setting.notSet'))}</span>
              </div>
              {found && <Chip tone={found.ok ? 'ok' : 'warn'}>{found.ok ? t('state.ready') : t('state.missing')}</Chip>}
              {value && detected && (
                <button className="link-btn" onClick={() => save({ [key]: '' })}>
                  {t('setting.reset')}
                </button>
              )}
              <button className="btn ghost small" onClick={() => browse(key, kind, ext)}>
                <FolderOpen size={14} /> {t('common.browse')}
              </button>
            </div>
          )
        })}
        <div className="option">
          <div className="grow">
            <b>{t('setting.steam')}</b>
            <small>{values?.steam_user ? t('steam.signedIn', { user: values.steam_user }) : t('steam.signedOutBody')}</small>
          </div>
          {values?.steam_user && (
            <button className="btn ghost small" onClick={() => api.call<Values>('vault.signout').then(setValues)}>
              <LogOut size={14} /> {t('steam.signOut')}
            </button>
          )}
        </div>
        <div className="option">
          <div className="grow">
            <b>{t('setting.language')}</b>
          </div>
          <Segmented<Lang> value={lang} onChange={setLang} options={[['en', 'English'], ['it', 'Italiano']]} />
        </div>
      </div>

      <div className="card about">
        <div className="grow">
          <div className="label">{t('about.label')}</div>
          <p>{t('about.body')}</p>
          <small>{t('about.credits')}</small>
        </div>
        <a className="btn ghost" href={REPO} target="_blank" rel="noreferrer">
          <ExternalLink size={15} /> GitHub
        </a>
      </div>
    </div>
  )
}
