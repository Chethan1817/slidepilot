import type { Engine } from './types'

/** How each agent engine is described in the UI. */
export const ENGINES: Record<Engine, { name: string; short: string; blurb: string; needs: string }> = {
  livekit: {
    name: 'LiveKit Agents',
    short: 'LiveKit',
    blurb: 'LiveKit runs the whole turn: speech-to-text, its own tool loop, and the voice.',
    needs: '',
  },
  langgraph_pipeline: {
    name: 'LangGraph pipeline',
    short: 'LangGraph',
    blurb: 'One LangGraph graph runs the whole turn: transcribe, think, speak. LiveKit only carries the audio.',
    needs: 'OPENAI_API_KEY and DEEPGRAM_API_KEY',
  },
}

/** The order engines are offered in. */
export const ENGINE_ORDER: Engine[] = ['livekit', 'langgraph_pipeline']
