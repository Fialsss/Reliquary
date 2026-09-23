import { useEffect } from 'react'
import { Crosshair, Gem, Paintbrush } from 'lucide-react'
import type { PageProps } from '../App'
import { useI18n } from '../i18n'
import { Chip, PageHead } from '../ui'

type Step = [key: string, state: 'proven' | 'building' | 'planned']

const TRACKS: { id: string; icon: typeof Crosshair; steps: Step[] }[] = [
  { id: 'weapons', icon: Crosshair, steps: [['weapons.registry', 'planned'], ['weapons.mesh', 'building'], ['weapons.assembly', 'planned']] },
  { id: 'skins', icon: Paintbrush, steps: [['skins.binding', 'proven'], ['skins.material', 'proven'], ['skins.catalog', 'planned'], ['skins.switcher', 'proven']] },
  { id: 'charms', icon: Gem, steps: [['charms.registry', 'planned'], ['charms.mesh', 'planned'], ['charms.socket', 'planned']] }
]

// The chain that recovered the original 552 Commando Glacier (Y5S4), kept as the reference method.
const CHAIN = [
  ['chain.cosmetic', '0x7C1AF8BDD'],
  ['chain.selection', '0x7C1AF8D87'],
  ['chain.bundle', '0x7C1AF8CDC'],
  ['chain.textures', '0x671B64941 · 0x671B64961 · 0x671B64966'],
  ['chain.archive', 'datapc64_merged_bnk_textures1.forge']
]

const TONE = { proven: 'ok', building: 'info', planned: 'muted' } as const

export default function Armory({ setArt }: PageProps) {
  const { t } = useI18n()
  useEffect(() => setArt({ seed: 23, hue: 350 }), [])

  return (
    <div className="stack">
      <PageHead eyebrow={t('armory.eyebrow')} title={t('armory.title')} sub={t('armory.sub')} right={<Chip tone="warn">{t('armory.status')}</Chip>} />
      <div className="grid tracks">
        {TRACKS.map(({ id, icon: Icon, steps }, i) => (
          <div key={id} className="card track" style={{ '--i': i } as React.CSSProperties}>
            <div className="card-title">
              <span className="tile-icon">
                <Icon size={17} strokeWidth={1.8} />
              </span>
              <b>{t(`track.${id}`)}</b>
            </div>
            <ul className="steps">
              {steps.map(([key, state]) => (
                <li key={key}>
                  <span>{t(`step.${key}`)}</span>
                  <Chip tone={TONE[state]}>{t(`stepState.${state}`)}</Chip>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="card chain">
        <div>
          <div className="label">{t('chain.label')}</div>
          <b>552 Commando · Glacier (Y5S4)</b>
          <p>{t('chain.body')}</p>
        </div>
        <ol>
          {CHAIN.map(([key, value]) => (
            <li key={key}>
              <small>{t(key)}</small>
              <span className="mono">{value}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
