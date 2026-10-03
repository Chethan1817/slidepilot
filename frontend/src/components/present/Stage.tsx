import clsx from 'clsx'
import { Download, Mic, RotateCcw, Volume2, Workflow, Zap } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ENGINE_ORDER, ENGINES } from '../../lib/engines'
import { formatDuration } from '../../lib/format'
import type { Deck, Engine, EngineInfo } from '../../lib/types'
import { AgentOrb } from '../AgentOrb'
import { Button } from '../Button'
import { buttonClass } from '../button-class'
import { SlideView } from '../SlideView'

interface StageProps {
  deck: Deck
  slideIndex: number
  overlay?: ReactNode
  /** Hint shown over a paused presentation. */
  showPausedHint: boolean
}

export function Stage({ deck, slideIndex, overlay, showPausedHint }: StageProps) {
  const slide = deck.slides[slideIndex]
  return (
    <div className="relative w-full max-w-[calc((100dvh-20rem)*16/9)] min-w-0">
      <div className="relative aspect-video overflow-hidden rounded-xl bg-white shadow-slide ring-1 ring-black/5">
        <AnimatePresence initial={false}>
          <motion.div
            key={slideIndex}
            className="absolute inset-0"
            initial={{ opacity: 0, scale: 1.012 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <SlideView slide={slide} theme={deck.theme} index={slideIndex} total={deck.slides.length} deckTitle={deck.title} />
          </motion.div>
        </AnimatePresence>

        <AnimatePresence>
          {showPausedHint && !overlay && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="absolute top-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full border border-line bg-white/95 px-3.5 py-1.5 text-[12.5px] whitespace-nowrap text-ink-2 shadow-elevated backdrop-blur"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-warn" />
              Paused · say “continue” or press
              <kbd className="rounded border border-line-strong bg-subtle px-1.5 font-mono text-[11px] text-ink">Space</kbd>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {overlay && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-20 flex items-center justify-center bg-white/55 p-3 backdrop-blur-[3px]"
            >
              {overlay}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      className={clsx('w-full max-w-sm rounded-2xl border border-line bg-white p-4 text-center shadow-elevated sm:p-6', className)}
    >
      {children}
    </motion.div>
  )
}

interface PreJoinProps {
  deck: Deck
  engines?: EngineInfo[]
  engine: Engine
  onEngineChange: (engine: Engine) => void
  canStart: boolean
  setupHint?: string
  error?: string | null
  onStart: () => void
}

export function PreJoinCard({ deck, engines, engine, onEngineChange, canStart, setupHint, error, onStart }: PreJoinProps) {
  return (
    <Card>
      <div className="hidden justify-center sm:flex">
        <AgentOrb state="listening" size={52} />
      </div>
      <h2 className="text-base font-semibold text-ink sm:mt-3 sm:text-lg">{error ? 'Let’s try that again' : 'Nova is ready to present'}</h2>
      <p className="mt-1 text-[13px] text-ink-2">
        {deck.slides.length} slides · about {deck.minutes} minutes · interrupt any time
      </p>
      <EnginePicker engines={engines} engine={engine} onChange={onEngineChange} />
      {error && <p className="mt-3 rounded-lg border border-live/15 bg-live-soft px-3 py-2 text-left text-[12.5px] leading-relaxed text-live">{error}</p>}
      <Button variant="primary" size="lg" className="mt-4 w-full sm:mt-5" onClick={onStart} disabled={!canStart}>
        <Mic className="h-4 w-4" /> {error ? 'Try again' : 'Start presentation'}
      </Button>
      <p className="mt-3 hidden text-xs text-ink-3 sm:block">{setupHint ?? 'Uses your microphone. To interrupt, just start talking.'}</p>
    </Card>
  )
}

const ENGINE_ICONS = { livekit: Zap, langgraph_pipeline: Workflow }

/** Segmented control for the agent engine; an engine the server can't run is disabled. */
function EnginePicker({ engines, engine, onChange }: { engines?: EngineInfo[]; engine: Engine; onChange: (engine: Engine) => void }) {
  return (
    <div className="mt-4 text-left">
      <div className="mb-1.5 hidden text-xs font-semibold text-ink-2 sm:block">Agent engine</div>
      <div role="radiogroup" aria-label="Agent engine" className="grid grid-cols-2 gap-1 rounded-xl bg-hover p-1">
        {ENGINE_ORDER.map((id) => {
          const Icon = ENGINE_ICONS[id]
          const info = engines?.find((e) => e.id === id)
          const disabled = info?.available === false
          return (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={engine === id}
              disabled={disabled}
              title={disabled ? `Needs ${ENGINES[id].needs} in backend/.env.local` : `${ENGINES[id].name}: ${ENGINES[id].blurb}`}
              onClick={() => onChange(id)}
              className={clsx(
                'flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] font-semibold transition',
                engine === id ? 'bg-white text-ink shadow-xs ring-1 ring-line' : 'text-ink-2 hover:text-ink',
                disabled && 'cursor-not-allowed opacity-45',
              )}
            >
              <Icon className={clsx('h-3.5 w-3.5', engine === id ? 'text-accent' : 'text-ink-3')} />
              {ENGINES[id].name}
            </button>
          )
        })}
      </div>
      <p className="mt-1.5 hidden text-xs leading-snug text-ink-3 sm:block">
        <span className="font-semibold text-ink-2">{ENGINES[engine].name}.</span> {ENGINES[engine].blurb}
      </p>
    </div>
  )
}

export function ConnectingCard({ label }: { label: string }) {
  return (
    <Card className="max-w-xs">
      <div className="flex justify-center">
        <AgentOrb state="initializing" size={50} />
      </div>
      <p className="mt-4 text-sm font-semibold text-ink">{label}</p>
      <p className="mt-1 text-xs text-ink-3">This usually takes a second or two.</p>
    </Card>
  )
}

export function AudioBlockedCard({ onEnable }: { onEnable: () => void }) {
  return (
    <Card className="max-w-xs">
      <p className="text-sm font-semibold text-ink">Your browser paused the audio</p>
      <Button variant="primary" className="mt-4 w-full" onClick={onEnable}>
        <Volume2 className="h-4 w-4" /> Turn on sound
      </Button>
    </Card>
  )
}

interface SummaryProps {
  durationMs: number
  slidesSeen: number
  totalSlides: number
  questions: number
  error?: string | null
  onRestart: () => void
  onDownload: () => void
}

export function SummaryCard({ durationMs, slidesSeen, totalSlides, questions, error, onRestart, onDownload }: SummaryProps) {
  return (
    <Card className="max-w-md text-left">
      <div className="text-xs font-semibold tracking-[0.08em] text-accent uppercase">Session complete</div>
      <h2 className="mt-1.5 text-lg font-semibold text-ink">{error ? 'The session was cut short' : 'Thanks for listening'}</h2>
      {error && <p className="mt-1 text-[13px] text-ink-2">{error}</p>}
      <dl className="mt-4 grid grid-cols-3 gap-2">
        {[
          ['Duration', formatDuration(durationMs)],
          ['Slides seen', `${slidesSeen}/${totalSlides}`],
          ['Questions', String(questions)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-line bg-subtle px-3 py-2.5">
            <dt className="text-[11px] text-ink-3">{label}</dt>
            <dd className="mt-0.5 text-base font-semibold text-ink tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-5 flex flex-wrap gap-2">
        <Button variant="primary" onClick={onRestart}>
          <RotateCcw className="h-4 w-4" /> Present again
        </Button>
        <Button variant="secondary" onClick={onDownload}>
          <Download className="h-4 w-4" /> Transcript
        </Button>
        <Link to="/" className={buttonClass('ghost')}>
          Library
        </Link>
      </div>
    </Card>
  )
}
