export type Layout = 'cover' | 'steps' | 'stat' | 'cards' | 'bullets' | 'closing'

export interface SlideItem {
  title: string
  body: string
  icon: string | null
  value: string | null
  share: number | null
}

export interface Slide {
  id: string
  layout: Layout
  title: string
  kicker: string | null
  subtitle: string | null
  items: SlideItem[]
  stat: { value: string; label: string } | null
  callout: { label: string; text: string } | null
  footnote: string | null
}

interface DeckBase {
  id: string
  title: string
  description: string
  category: string
  theme: string
  minutes: number
  suggested_questions: string[]
}

export interface DeckSummary extends DeckBase {
  slide_count: number
  cover: Slide
}

export interface Deck extends DeckBase {
  slides: Slide[]
}

export type Stage = 'stt' | 'llm' | 'tts'

/** The interchangeable "brains" a session can run on. */
export type Engine = 'livekit' | 'langgraph_pipeline'

export interface EngineInfo {
  id: Engine
  name: string
  available: boolean
  llm: string
}

export interface Health {
  status: string
  livekit_configured: boolean
  livekit: { url: string; cloud: boolean }
  models: { llm: string; stt: string; tts: string }
  /** Each stage's providers, primary first; the rest take over if it fails. */
  pipeline: Record<Stage, { provider: string; model: string }[]>
  engines: EngineInfo[]
}

export interface SessionCredentials {
  server_url: string
  participant_token: string
  room_name: string
  participant_identity: string
}

export type PresentMode = 'idle' | 'presenting' | 'paused' | 'finished'
/** Why the state changed; `end` means Nova said goodbye and the session should close. */
export type ChangeReason = 'start' | 'advance' | 'agent' | 'resume' | 'user' | 'pause' | 'finish' | 'end'

/** Published by the agent in its `slidepilot.state` participant attribute. */
export interface PresenterState {
  slide: number
  mode: PresentMode
  reason: ChangeReason
  seq: number
  engine?: Engine
}
