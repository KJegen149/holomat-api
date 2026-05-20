import { useState, useCallback } from 'react'
import { X, Delete, CornerDownLeft, ChevronUp } from 'lucide-react'

interface Props {
  onClose: () => void
}

const ROWS_LOWER = [
  ['1','2','3','4','5','6','7','8','9','0','-','='],
  ['q','w','e','r','t','y','u','i','o','p'],
  ['a','s','d','f','g','h','j','k','l',';',"'"],
  ['z','x','c','v','b','n','m',',','.','/'],
]

const ROWS_UPPER = [
  ['!','@','#','$','%','^','&','*','(',')','_','+'],
  ['Q','W','E','R','T','Y','U','I','O','P'],
  ['A','S','D','F','G','H','J','K','L',':','"'],
  ['Z','X','C','V','B','N','M','<','>','?'],
]

function getInputProto(el: HTMLInputElement | HTMLTextAreaElement) {
  return el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype
}

function typeInto(el: HTMLInputElement | HTMLTextAreaElement, char: string) {
  const nativeSetter = Object.getOwnPropertyDescriptor(getInputProto(el), 'value')?.set
  const start = el.selectionStart ?? el.value.length
  const end   = el.selectionEnd   ?? el.value.length
  const next  = el.value.slice(0, start) + char + el.value.slice(end)
  nativeSetter?.call(el, next)
  el.selectionStart = el.selectionEnd = start + char.length
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

function backspaceInto(el: HTMLInputElement | HTMLTextAreaElement) {
  const nativeSetter = Object.getOwnPropertyDescriptor(getInputProto(el), 'value')?.set
  const start = el.selectionStart ?? el.value.length
  const end   = el.selectionEnd   ?? el.value.length
  let next: string, pos: number
  if (start !== end) {
    next = el.value.slice(0, start) + el.value.slice(end)
    pos  = start
  } else if (start > 0) {
    next = el.value.slice(0, start - 1) + el.value.slice(start)
    pos  = start - 1
  } else return
  nativeSetter?.call(el, next)
  el.selectionStart = el.selectionEnd = pos
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

function getTarget(): HTMLInputElement | HTMLTextAreaElement | null {
  const el = document.activeElement
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return el
  return null
}

const KEY_BASE =
  'h-10 min-w-[2.25rem] px-2 flex items-center justify-center rounded-sm border ' +
  'font-mono text-[11px] tracking-wide select-none cursor-pointer transition-colors ' +
  'bg-j-surf border-j-border text-j-text hover:bg-j-border hover:text-j-cyan active:scale-95'

const KEY_ACCENT =
  'h-10 px-3 flex items-center justify-center rounded-sm border ' +
  'font-mono text-[10px] tracking-[0.1em] uppercase select-none cursor-pointer transition-colors ' +
  'bg-j-border border-j-border text-j-muted hover:text-j-cyan hover:bg-j-border active:scale-95'

export default function OnScreenKeyboard({ onClose }: Props) {
  const [shifted, setShifted] = useState(false)

  const press = useCallback((char: string) => {
    const el = getTarget()
    if (el) typeInto(el, char)
    if (shifted) setShifted(false)
  }, [shifted])

  const bksp = useCallback(() => {
    const el = getTarget()
    if (el) backspaceInto(el)
  }, [])

  const enter = useCallback(() => {
    const el = getTarget()
    if (!el) return
    if (el instanceof HTMLTextAreaElement) {
      typeInto(el, '\n')
    } else {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      el.form?.requestSubmit()
    }
  }, [])

  const rows = shifted ? ROWS_UPPER : ROWS_LOWER

  // onMouseDown preventDefault keeps focus on the active input
  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-50 border-t border-j-border bg-j-surf shadow-2xl"
      onMouseDown={e => e.preventDefault()}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-j-border">
        <span className="font-mono text-[10px] text-j-cdim tracking-[0.15em] uppercase">On-Screen Keyboard</span>
        <button
          type="button"
          onClick={onClose}
          className="text-j-muted hover:text-j-err transition-colors p-1"
        >
          <X size={14} />
        </button>
      </div>

      {/* Keys */}
      <div className="px-4 py-3 space-y-1.5">
        {rows.map((row, ri) => (
          <div key={ri} className="flex gap-1 justify-center">
            {ri === 3 && (
              <button
                type="button"
                onClick={() => setShifted(s => !s)}
                className={`${KEY_ACCENT} ${shifted ? 'text-j-cyan border-j-cyan bg-j-cyan/10' : ''}`}
              >
                <ChevronUp size={14} />
              </button>
            )}
            {row.map(ch => (
              <button
                key={ch}
                type="button"
                onClick={() => press(ch)}
                className={KEY_BASE}
              >
                {ch}
              </button>
            ))}
            {ri === 0 && (
              <button type="button" onClick={bksp} className={`${KEY_ACCENT} gap-1.5`}>
                <Delete size={13} />
              </button>
            )}
          </div>
        ))}

        {/* Bottom row: space + enter */}
        <div className="flex gap-1 justify-center">
          <button
            type="button"
            onClick={() => press(' ')}
            className={`${KEY_BASE} flex-1 max-w-xs`}
          >
            SPACE
          </button>
          <button
            type="button"
            onClick={enter}
            className={`${KEY_ACCENT} gap-1.5`}
          >
            <CornerDownLeft size={13} />
            Enter
          </button>
        </div>
      </div>
    </div>
  )
}
