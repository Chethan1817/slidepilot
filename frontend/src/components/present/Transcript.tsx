import clsx from 'clsx'
import { Keyboard, MessagesSquare, Send } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Phase } from '../../lib/session'
import type { TranscriptEntry } from '../../lib/transcript'

export function TranscriptPanel({ entries, phase }: { entries: TranscriptEntry[]; phase: Phase }) {
  const scroller = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  useEffect(() => {
    const el = scroller.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [entries])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <h3 className="text-xs font-semibold tracking-[0.06em] text-ink-3 uppercase">Transcript</h3>
        {phase === 'live' && (
          <span className="flex items-center gap-1.5 rounded-full bg-live-soft px-2 py-0.5 text-[11px] font-semibold text-live">
            <span className="h-1.5 w-1.5 animate-blink rounded-full bg-live" /> Live
          </span>
        )}
      </div>
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}
        className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pb-4"
      >
        {entries.length === 0 ? (
          <div className="flex flex-col items-center px-4 pt-8 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-subtle text-ink-3 ring-1 ring-line">
              <MessagesSquare className="h-5 w-5" />
            </span>
            <p className="mt-3 text-[13px] leading-relaxed text-ink-2">
              {phase === 'live'
                ? 'Nova is about to start. What you both say shows up here.'
                : 'Start the presentation and the conversation will appear here.'}
            </p>
          </div>
        ) : (
          entries.map((entry) => <Line key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  )
}

function Line({ entry }: { entry: TranscriptEntry }) {
  if (entry.speaker === 'you') {
    return (
      <div className="flex justify-end">
        <div
          className={clsx(
            'max-w-[86%] rounded-2xl rounded-tr-md px-3.5 py-2 text-[14px] leading-relaxed text-white shadow-xs',
            entry.final ? 'bg-accent' : 'bg-accent/70',
          )}
        >
          {entry.typed && <Keyboard className="mr-1.5 mb-0.5 inline h-3.5 w-3.5 text-white/75" aria-label="Typed" />}
          {entry.text}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-2.5">
      <span className="mt-0.5 h-6 w-6 shrink-0 rounded-full bg-[conic-gradient(from_0deg,#a5b4fc,#4f46e5,#0891b2,#22d3ee,#a5b4fc)] ring-2 ring-white" />
      <div className="min-w-0 max-w-[88%]">
        <div className="mb-1 text-[11.5px] font-semibold text-ink-2">Nova</div>
        <p className="rounded-2xl rounded-tl-md border border-line bg-subtle px-3.5 py-2 text-[14px] leading-relaxed text-ink">
          {entry.text}
        </p>
      </div>
    </div>
  )
}

interface ComposerProps {
  enabled: boolean
  suggestions: string[]
  onAsk: (text: string) => void
}

export function Composer({ enabled, suggestions, onAsk }: ComposerProps) {
  const [text, setText] = useState('')
  // Suggestions already asked drop out, so the next ones come into view.
  const [asked, setAsked] = useState<ReadonlySet<string>>(() => new Set())
  const remaining = suggestions.filter((question) => !asked.has(question.toLowerCase()))

  const ask = (question: string) => {
    setAsked((current) => new Set(current).add(question.toLowerCase()))
    onAsk(question)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const question = text.trim()
    if (!question || !enabled) return
    ask(question)
    setText('')
  }

  return (
    <div className="border-t border-line bg-white p-3">
      {remaining.length > 0 && (
        <div className="scroll-thin -mx-3 mb-2.5 flex gap-1.5 overflow-x-auto px-3 pb-0.5">
          {remaining.map((question) => (
            <button
              key={question}
              type="button"
              disabled={!enabled}
              onClick={() => ask(question)}
              className="shrink-0 rounded-full border border-line bg-white px-2.5 py-1 text-[12px] font-medium text-ink-2 shadow-xs transition hover:border-accent/40 hover:text-accent disabled:opacity-50"
            >
              {question}
            </button>
          ))}
        </div>
      )}
      <form
        onSubmit={submit}
        className="flex items-center gap-2 rounded-xl border border-line-strong bg-white pr-1.5 pl-3.5 shadow-xs transition focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10"
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={!enabled}
          placeholder={enabled ? 'Type a question, or just speak…' : 'Questions open once Nova is live'}
          className="h-10 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-3 disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          aria-label="Send question"
          disabled={!enabled || !text.trim()}
          className="flex h-7.5 w-7.5 items-center justify-center rounded-lg bg-accent text-white transition hover:bg-accent-hover disabled:bg-hover disabled:text-ink-3"
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  )
}
