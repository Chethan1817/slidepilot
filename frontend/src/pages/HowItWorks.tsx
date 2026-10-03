import { ArrowRight, AudioLines, Brain, Ear, Hand, Keyboard, Layers, MessageSquareQuote, Mic, Navigation, Play, Workflow, Zap } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AppShell } from '../components/AppShell'
import { buttonClass } from '../components/button-class'
import { api, useQuery } from '../lib/api'
import { prettyModel, prettyVendor } from '../lib/format'

const STEPS = [
  {
    icon: Layers,
    title: 'Pick a deck',
    body: 'Every deck carries speaker notes, so Nova knows far more than the slides show and can go deeper when you ask.',
  },
  {
    icon: Hand,
    title: 'Talk over it',
    body: 'Interrupt mid-sentence. Nova stops speaking the moment you start, listens, and answers in a few sentences.',
  },
  {
    icon: Navigation,
    title: 'It follows you',
    body: 'Ask about something on another slide and Nova jumps there to answer. Say "continue" to pick up where it left off, or "bye" to wrap up.',
  },
]

const TRY = [
  'How fast does a voice agent need to respond?',
  'What does barge-in mean?',
  'Skip ahead to the slide about tools.',
  'Okay, continue.',
  'Start over.',
  "Thanks, that's all for today. Bye!",
]

const SHORTCUTS = [
  ['← →', 'Previous or next slide'],
  ['Space', 'Pause or continue'],
  ['M', 'Mute or unmute your microphone'],
]

export function HowItWorksPage() {
  const health = useQuery('health', api.health)
  const pipeline = health.data?.pipeline
  const stt = pipeline ? prettyVendor(pipeline.stt[0].provider) : '…'
  const llm = pipeline ? prettyModel(pipeline.llm[0].model) : '…'
  const tts = pipeline ? prettyVendor(pipeline.tts[0].provider) : '…'
  const graphEngine = health.data?.engines.find((engine) => engine.id === 'langgraph_pipeline')
  const graphLlm = graphEngine ? prettyModel(graphEngine.llm) : '…'

  return (
    <AppShell
      title="How it works"
      subtitle="What happens when you talk to Nova, and what to try."
      actions={
        <Link to="/" className={buttonClass('primary')}>
          <Play className="h-4 w-4" /> Start a session
        </Link>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        {STEPS.map((step, i) => (
          <div key={step.title} className="rounded-2xl border border-line bg-white p-6 shadow-card">
            <div className="flex items-center justify-between">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
                <step.icon className="h-5 w-5" />
              </span>
              <span className="font-mono text-xs text-ink-3">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <h3 className="mt-5 font-semibold text-ink">{step.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{step.body}</p>
          </div>
        ))}
      </div>

      <section className="mt-6 rounded-2xl border border-line bg-white p-6 shadow-card">
        <h2 className="font-semibold text-ink">Two separate pipelines</h2>
        <p className="mt-1 text-sm text-ink-2">
          Pick one on the start card. In both, LiveKit carries your voice and Nova&apos;s over WebRTC; what happens in between is
          different. Every step streams, so Nova starts speaking before the whole reply is written.
        </p>
        <div className="mt-5 space-y-5">
          <PipelineRow icon={<Zap className="h-4 w-4" />} name="LiveKit Agents" note="LiveKit runs every step">
            <PipelineStep icon={<Mic className="h-4 w-4" />} label="Your voice" detail="WebRTC via LiveKit" />
            <Arrow />
            <PipelineStep icon={<Ear className="h-4 w-4" />} label="Speech-to-text" detail={`LiveKit · ${stt}`} />
            <Arrow />
            <PipelineStep icon={<Brain className="h-4 w-4" />} label="LLM + slide tools" detail={`LiveKit tool loop · ${llm}`} />
            <Arrow />
            <PipelineStep icon={<AudioLines className="h-4 w-4" />} label="Voice" detail={`LiveKit · ${tts}`} />
          </PipelineRow>
          <PipelineRow icon={<Workflow className="h-4 w-4" />} name="LangGraph pipeline" note="One LangGraph graph runs every step">
            <PipelineStep icon={<Mic className="h-4 w-4" />} label="Your voice" detail="WebRTC via LiveKit" />
            <Arrow />
            <div className="relative flex flex-wrap items-center gap-2 rounded-2xl border border-dashed border-accent/40 bg-accent-soft/40 px-2 pt-3.5 pb-2">
              <span className="absolute -top-2.5 left-3 rounded bg-white px-1.5 text-[10.5px] font-semibold tracking-[0.06em] text-accent uppercase">
                LangGraph graph
              </span>
              <PipelineStep icon={<Ear className="h-4 w-4" />} label="transcribe" detail="Deepgram, streaming" />
              <Arrow />
              <PipelineStep icon={<Brain className="h-4 w-4" />} label="think" detail={`${graphLlm} + slide tools`} />
              <Arrow />
              <PipelineStep icon={<AudioLines className="h-4 w-4" />} label="speak" detail={`${tts}, as think writes`} />
            </div>
          </PipelineRow>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-line bg-white p-6 shadow-card">
        <h2 className="font-semibold text-ink">Pick the agent engine</h2>
        <p className="mt-1 text-sm text-ink-2">
          Before you start, choose which engine runs Nova. Both present, answer and change slides the same way, but they are two
          separate pipelines: one built on LiveKit Agents, one built in LangGraph.
        </p>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <EngineCard
            icon={<Zap className="h-4 w-4" />}
            name="LiveKit Agents"
            body="LiveKit runs the whole turn: streaming speech-to-text, the LLM calling LiveKit function tools (show a slide, resume, present from a slide) in LiveKit's own tool loop, and the voice."
          />
          <EngineCard
            icon={<Workflow className="h-4 w-4" />}
            name="LangGraph pipeline"
            body="One LangGraph graph runs the whole turn: a transcribe node (Deepgram), a think node (a LangGraph agent whose tools change slides), and a speak node (Deepgram Aura). LiveKit only carries the audio."
          />
        </div>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
          <h2 className="flex items-center gap-2 font-semibold text-ink">
            <MessageSquareQuote className="h-[18px] w-[18px] text-accent" /> Things to try saying
          </h2>
          <ul className="mt-4 space-y-2">
            {TRY.map((phrase) => (
              <li key={phrase} className="flex items-center gap-3 rounded-xl border border-line bg-subtle px-3.5 py-2.5 text-sm text-ink">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />“{phrase}”
              </li>
            ))}
          </ul>
        </section>
        <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
          <h2 className="flex items-center gap-2 font-semibold text-ink">
            <Keyboard className="h-[18px] w-[18px] text-accent" /> Keyboard shortcuts
          </h2>
          <dl className="mt-4 divide-y divide-line">
            {SHORTCUTS.map(([keys, action]) => (
              <div key={keys} className="flex items-center justify-between py-2.5 text-sm">
                <dt className="text-ink-2">{action}</dt>
                <dd>
                  <kbd className="rounded-md border border-line-strong bg-subtle px-2 py-0.5 font-mono text-xs text-ink shadow-xs">
                    {keys}
                  </kbd>
                </dd>
              </div>
            ))}
          </dl>
          <Link to="/settings" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-accent hover:text-accent-hover">
            See the full configuration <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </div>
    </AppShell>
  )
}

function PipelineStep({ icon, label, detail }: { icon: ReactNode; label: string; detail: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-subtle px-3.5 py-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-accent shadow-xs ring-1 ring-line">{icon}</span>
      <div className="leading-tight">
        <div className="text-[13px] font-semibold text-ink">{label}</div>
        <div className="text-xs text-ink-2">{detail}</div>
      </div>
    </div>
  )
}

function EngineCard({ icon, name, body }: { icon: ReactNode; name: string; body: string }) {
  return (
    <div className="rounded-xl border border-line bg-subtle p-4">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-accent shadow-xs ring-1 ring-line">{icon}</span>
        <span className="text-sm font-semibold text-ink">{name}</span>
      </div>
      <p className="mt-2.5 text-[13px] leading-relaxed text-ink-2">{body}</p>
    </div>
  )
}

function PipelineRow({ icon, name, note, children }: { icon: ReactNode; name: string; note: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-accent-soft text-accent">{icon}</span>
        <span className="text-sm font-semibold text-ink">{name}</span>
        <span className="text-xs text-ink-3">· {note}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

function Arrow() {
  return <ArrowRight className="hidden h-4 w-4 text-ink-3 sm:block" />
}
