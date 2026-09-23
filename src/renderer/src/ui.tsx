import { useEffect, useState, type ReactNode } from 'react'
import { Check as CheckIcon, Trash2 } from 'lucide-react'

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

/** A destructive action in two clicks: the first arms it (red, "confirm"), the second runs it. */
export function ConfirmButton({ label, confirm, onConfirm, small = true }: { label: string; confirm: string; onConfirm: () => void; small?: boolean }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const timer = setTimeout(() => setArmed(false), 3500)
    return () => clearTimeout(timer)
  }, [armed])
  return (
    <button
      className={`btn ghost danger${small ? ' small' : ''}${armed ? ' armed' : ''}`}
      onClick={() => {
        if (armed) onConfirm()
        setArmed(!armed)
      }}
    >
      <Trash2 size={14} /> {armed ? confirm : label}
    </button>
  )
}
