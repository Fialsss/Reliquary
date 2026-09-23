import type { ReactNode } from 'react'
import { Check as CheckIcon } from 'lucide-react'

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'muted'

export function Chip({ tone = 'muted', dot = true, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return <span className={`chip ${tone}${dot ? ' dot' : ''}`}>{children}</span>
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden="true" />
}

export function PageHead({ eyebrow, title, sub, right }: { eyebrow: string; title: ReactNode; sub?: string; right?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {right && <div className="page-head-right">{right}</div>}
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (value: T) => void }) {
  return (
    <div className="segmented" role="tablist">
      {options.map(([id, label]) => (
        <button key={id} role="tab" aria-selected={value === id} className={value === id ? 'on' : ''} onClick={() => onChange(id)}>
          {label}
        </button>
      ))}
    </div>
  )
}

export function Check({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <button className={`check${checked ? ' on' : ''}`} role="checkbox" aria-checked={checked} aria-label={label} onClick={onChange}>
      {checked && <CheckIcon size={12} strokeWidth={3} />}
    </button>
  )
}
