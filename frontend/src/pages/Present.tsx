import { RoomAudioRenderer, RoomContext, useAudioPlayback, useVoiceAssistant, type AgentState } from '@livekit/components-react'
import { ArrowLeft, ChevronRight, PhoneOff } from 'lucide-react'
import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { buttonClass } from '../components/button-class'
import { LogoMark } from '../components/Logo'
import { AgentCard } from '../components/present/AgentCard'
import { ControlBar, ThumbnailRail } from '../components/present/Controls'
import { AudioBlockedCard, ConnectingCard, PreJoinCard, Stage, SummaryCard } from '../components/present/Stage'
import { Composer, TranscriptPanel } from '../components/present/Transcript'
import { StatusPill } from '../components/StatusPill'
import { api, useQuery } from '../lib/api'
import { formatDuration, useNow } from '../lib/format'
import { useToast, type Notify } from '../lib/toast'
import { useTranscriptEntries, type TypedMessage } from '../lib/transcript'
import {
  ERROR_ATTRIBUTE,
  LATENCY_ATTRIBUTE,
  STATE_ATTRIBUTE,
  parsePresenterState,
  saveEngine,
  savedEngine,
  useAgentJoinTimeout,
  useLiveSession,
  type Phase,
} from '../lib/session'
import type { Deck, Engine, Health, PresenterState } from '../lib/types'

export function PresentPage() {
  const { deckId = '' } = useParams()
  const deck = useQuery(`deck:${deckId}`, () => api.deck(deckId))
  const health = useQuery('health', api.health)

  if (deck.status === 'loading') {
    return <div className="flex h-dvh items-center justify-center text-sm text-ink-3">Loading deck…</div>
  }
  if (deck.status === 'error') {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-ink-2">{deck.error}</p>
        <Link to="/" className={buttonClass('secondary')}>
          <ArrowLeft className="h-4 w-4" /> Back to library
        </Link>
      </div>
    )
  }
  return <PresentRoom deck={deck.data} health={health.data} healthError={health.error} />
}

interface RoomProps {
  deck: Deck
  health?: Health
  healthError?: string
}

// After Nova's goodbye, how long to let the last of its audio play before closing.
const GOODBYE_GRACE_MS = 600

function PresentRoom(props: RoomProps) {
  const session = useLiveSession(props.deck.id)
  // Every start gets a fresh view, so the transcript and stats begin empty.
  const [run, setRun] = useState(0)
  const [picked, setPicked] = useState<Engine>(savedEngine)
  // Fall back to LiveKit Agents if the saved choice isn't available on this server.
  const engine = props.health?.engines.find((e) => e.id === picked)?.available === false ? 'livekit' : picked

  const start = () => {
    setRun((n) => n + 1)
    saveEngine(engine)
    void session.start(engine)
  }

  return (
    <RoomContext.Provider value={session.room}>
      <RoomAudioRenderer />
      <PresentView
        key={run}
        {...props}
        session={session}
        engine={engine}
        onEngineChange={setPicked}
        onStart={start}
        onRestart={start}
      />
    </RoomContext.Provider>
  )
}

type Session = ReturnType<typeof useLiveSession>

interface ViewProps extends RoomProps {
  session: Session
  engine: Engine
  onEngineChange: (engine: Engine) => void
  onStart: () => void
  onRestart: () => void
}

function PresentView({ deck, health, healthError, session, engine, onEngineChange, onStart, onRestart }: ViewProps) {
  const notify = useToast()
  const { room, phase, end: endSession } = session
  const { agent, state: agentState, audioTrack, agentAttributes } = useVoiceAssistant()
  const { canPlayAudio, startAudio } = useAudioPlayback(room)

  const live = phase === 'live'
  const rawState = live ? agentAttributes?.[STATE_ATTRIBUTE] : undefined
  const presenter = useMemo(() => parsePresenterState(rawState), [rawState])
  const ready = live && !!agent && !!presenter
  const latencyMs = Number(agentAttributes?.[LATENCY_ATTRIBUTE]) || null

  // Nova counts as joined once it has published its first presentation state.
  useAgentJoinTimeout(phase, ready, session.fail)

  // Which slide is on screen: the agent decides while live, otherwise you browse freely.
  // `shown` also keeps the last live slide on screen after the session ends.
  const [shown, setShown] = useState(0)
  const [pending, setPending] = useState<{ slide: number; seq: number } | null>(null)
  const agentSlide = presenter ? (pending?.seq === presenter.seq ? pending.slide : presenter.slide) : null
  if (agentSlide !== null && agentSlide !== shown) setShown(agentSlide)
  const slideIndex = agentSlide ?? shown

  const [visited, setVisited] = useState<ReadonlySet<number>>(() => new Set())
  if (agentSlide !== null && !visited.has(agentSlide)) setVisited(new Set(visited).add(agentSlide))

  useAgentJumpToasts(presenter, deck, notify)

  // Nova said goodbye: close the session, which brings up the summary.
  const saidGoodbye = presenter?.reason === 'end'
  useEffect(() => {
    if (!saidGoodbye) return
    const id = window.setTimeout(() => void endSession(), GOODBYE_GRACE_MS)
    return () => window.clearTimeout(id)
  }, [saidGoodbye, endSession])

  useEffect(() => {
    if (session.micBlocked) notify('error', 'Microphone is blocked', 'Allow mic access in your browser, or type your questions.')
  }, [session.micBlocked, notify])

  // The agent reports pipeline failures (an out-of-credit API key, say) so silence is explained.
  const rawError = live ? agentAttributes?.[ERROR_ATTRIBUTE] : undefined
  useEffect(() => {
    if (!rawError) return
    try {
      notify('error', 'Nova ran into a problem', (JSON.parse(rawError) as { message: string }).message)
    } catch {
      notify('error', 'Nova ran into a problem')
    }
  }, [rawError, notify])

  const callAgent = useCallback(
    async (method: string, payload: object = {}) => {
      if (!agent) return
      try {
        await room.localParticipant.performRpc({
          destinationIdentity: agent.identity,
          method,
          payload: JSON.stringify(payload),
        })
      } catch {
        notify('error', "Nova didn't respond to that", 'Give it a second and try again.')
      }
    },
    [agent, room, notify],
  )

  const goTo = (index: number) => {
    if (index < 0 || index >= deck.slides.length || index === slideIndex) return
    if (!live) return setShown(index)
    if (!ready || !presenter) return
    setPending({ slide: index, seq: presenter.seq })
    void callAgent('slidepilot.goto', { slide: index })
  }
  const pause = () => void callAgent('slidepilot.pause')
  const resume = () => void callAgent('slidepilot.resume', presenter?.mode === 'finished' ? { slide: 0 } : {})

  const [typed, setTyped] = useState<TypedMessage[]>([])
  const entries = useTranscriptEntries(room, typed)
  const ask = (text: string) => {
    if (!ready) return
    setTyped((current) => [...current, { id: crypto.randomUUID(), text, at: Date.now() }])
    room.localParticipant.sendText(text, { topic: 'lk.chat' }).catch(() => notify('error', "Couldn't send your question"))
  }

  const toggleMic = () => {
    room.localParticipant
      .setMicrophoneEnabled(!room.localParticipant.isMicrophoneEnabled)
      .catch(() => notify('error', 'Microphone is blocked', 'Allow mic access in your browser settings.'))
  }

  // Keyboard: arrows move slides, Space pauses or continues, M toggles the mic.
  const onKey = useEffectEvent((event: KeyboardEvent) => {
    const target = event.target as HTMLElement
    if (target.closest('input, textarea, [contenteditable]') || event.metaKey || event.ctrlKey || event.altKey) return
    if (event.key === 'ArrowRight') goTo(slideIndex + 1)
    else if (event.key === 'ArrowLeft') goTo(slideIndex - 1)
    else if (event.key === 'm' && live) toggleMic()
    else if (event.key === ' ' && ready && !target.closest('button')) {
      event.preventDefault()
      if (presenter?.mode === 'presenting') pause()
      else resume()
    }
  })
  useEffect(() => {
    const handler = (event: KeyboardEvent) => onKey(event)
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const downloadTranscript = () => {
    const lines = entries.map((e) => `${e.speaker === 'nova' ? 'Nova' : 'You'}: ${e.text}`)
    const blob = new Blob([`${deck.title}\n\n${lines.join('\n\n')}\n`], { type: 'text/plain' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${deck.id}-transcript.txt`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const canStart = health?.livekit_configured !== false && !healthError
  const setupHint = healthError
    ? "The API isn't reachable. Start the backend on port 8000."
    : health?.livekit_configured === false
      ? 'Add your LiveKit keys to backend/.env.local to go live.'
      : undefined

  const overlay = (() => {
    if (phase === 'idle' || phase === 'error')
      return (
        <PreJoinCard
          deck={deck}
          engines={health?.engines}
          engine={engine}
          onEngineChange={onEngineChange}
          canStart={canStart}
          setupHint={setupHint}
          error={session.error}
          onStart={onStart}
        />
      )
    if (phase === 'connecting') return <ConnectingCard label="Connecting to the room…" />
    if (live && !ready) return <ConnectingCard label="Nova is joining…" />
    if (live && !canPlayAudio) return <AudioBlockedCard onEnable={startAudio} />
    if (phase === 'ended')
      return (
        <SummaryCard
          durationMs={session.endedAt && session.startedAt ? session.endedAt - session.startedAt : 0}
          slidesSeen={visited.size}
          totalSlides={deck.slides.length}
          questions={entries.filter((e) => e.speaker === 'you' && e.final).length}
          error={session.error}
          onRestart={onRestart}
          onDownload={downloadTranscript}
        />
      )
    return undefined
  })()

  const displayState: AgentState = live ? agentState : 'disconnected'

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas">
      <RoomHeader deck={deck} phase={phase} startedAt={session.startedAt} health={health} healthError={healthError} onEnd={session.end} />

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 items-center justify-center px-4 pt-4 pb-2 sm:px-10 sm:pt-7">
            <Stage deck={deck} slideIndex={slideIndex} overlay={overlay} showPausedHint={ready && presenter?.mode === 'paused'} />
          </div>
          <ThumbnailRail
            deck={deck}
            current={slideIndex}
            disabled={live && !ready}
            speaking={live && agentState === 'speaking'}
            onSelect={goTo}
          />
          <div className="flex shrink-0 justify-center px-4 pt-1 pb-4 sm:pb-5">
            <ControlBar
              live={live}
              ready={ready}
              mode={presenter?.mode}
              slideIndex={slideIndex}
              slideCount={deck.slides.length}
              onPrev={() => goTo(slideIndex - 1)}
              onNext={() => goTo(slideIndex + 1)}
              onPause={pause}
              onResume={resume}
              onStart={onStart}
              startDisabled={!canStart || phase === 'connecting'}
              micBlocked={session.micBlocked}
              onMicError={() => notify('error', 'Microphone is blocked', 'Allow mic access in your browser settings.')}
            />
          </div>
        </main>

        <aside className="flex h-[44dvh] min-h-0 shrink-0 flex-col border-t border-line bg-white lg:h-auto lg:w-[380px] lg:border-t-0 lg:border-l">
          <AgentCard
            state={displayState}
            track={audioTrack}
            status={statusLabel(phase, displayState, presenter, !!agent)}
            latencyMs={live ? latencyMs : null}
            slideLabel={`${slideIndex + 1} / ${deck.slides.length}`}
            modeLabel={modeLabel(phase, presenter)}
            engine={presenter?.engine ?? engine}
          />
          <TranscriptPanel entries={entries} phase={phase} />
          <Composer enabled={ready} suggestions={deck.suggested_questions} onAsk={ask} />
        </aside>
      </div>
    </div>
  )
}

function useAgentJumpToasts(presenter: PresenterState | null, deck: Deck, notify: Notify) {
  const lastSeq = useRef<number | null>(null)
  useEffect(() => {
    if (!presenter || presenter.seq === lastSeq.current) return
    const first = lastSeq.current === null
    lastSeq.current = presenter.seq
    if (!first && presenter.reason === 'agent') {
      notify('agent', `Nova jumped to slide ${presenter.slide + 1}`, deck.slides[presenter.slide]?.title)
    }
  }, [presenter, deck, notify])
}

interface HeaderProps {
  deck: Deck
  phase: Phase
  startedAt: number | null
  health?: Health
  healthError?: string
  onEnd: () => void
}

function RoomHeader({ deck, phase, startedAt, health, healthError, onEnd }: HeaderProps) {
  const live = phase === 'live'
  const now = useNow(live)
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-white px-4 sm:px-6">
      <Link to="/" aria-label="Slidepilot library" className="rounded-md focus-visible:outline-2 focus-visible:outline-accent">
        <LogoMark className="h-7 w-7" />
      </Link>
      <nav className="flex min-w-0 items-center gap-2 text-sm">
        <Link to="/" className="hidden font-medium text-ink-2 hover:text-ink sm:inline">
          Library
        </Link>
        <ChevronRight className="hidden h-4 w-4 text-ink-3 sm:inline" />
        <span className="truncate font-semibold text-ink">{deck.title}</span>
      </nav>
      <div className="ml-auto flex shrink-0 items-center gap-2.5">
        {live && startedAt && (
          <span className="flex items-center gap-2 rounded-full border border-live/20 bg-live-soft px-2.5 py-1 text-[12px] font-semibold text-live tabular-nums">
            <span className="h-1.5 w-1.5 animate-blink rounded-full bg-live" /> LIVE {formatDuration(now - startedAt)}
          </span>
        )}
        <div className="hidden md:block">
          <StatusPill health={health} error={healthError} />
        </div>
        {live && (
          <Button variant="danger" size="sm" onClick={onEnd}>
            <PhoneOff className="h-3.5 w-3.5" /> <span className="hidden sm:inline">End session</span>
          </Button>
        )}
      </div>
    </header>
  )
}

function statusLabel(phase: Phase, state: AgentState, presenter: PresenterState | null, agentJoined: boolean): string {
  if (phase === 'idle') return 'Ready when you are'
  if (phase === 'connecting') return 'Connecting…'
  if (phase === 'ended') return 'Session ended'
  if (phase === 'error') return 'Offline'
  if (!agentJoined) return 'Joining the room…'
  switch (state) {
    case 'speaking':
      return presenter?.mode === 'presenting' ? `Presenting slide ${presenter.slide + 1}` : 'Answering'
    case 'thinking':
      return 'Thinking…'
    case 'listening':
      if (presenter?.mode === 'paused') return 'Listening · presentation paused'
      if (presenter?.mode === 'finished') return 'Listening · ask anything'
      return 'Listening'
    default:
      return 'Getting ready…'
  }
}

function modeLabel(phase: Phase, presenter: PresenterState | null): string {
  if (phase !== 'live' || !presenter) return phase === 'ended' ? 'Ended' : 'Preview'
  return { idle: 'Starting', presenting: 'Presenting', paused: 'Paused', finished: 'Q&A' }[presenter.mode]
}
