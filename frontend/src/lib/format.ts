import { useEffect, useState } from 'react'

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

/** Re-renders every `intervalMs` while `active`, returning the current time. */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [active, intervalMs])
  return now
}

const MODEL_NAMES: Record<string, string> = {
  'claude-opus-5-5': 'Claude Opus 5.5',
  'claude-sonnet-5-5': 'Claude Sonnet 5.5',
  'claude-haiku-4-5': 'Claude Haiku 4.5',
  'claude-fable-5-1': 'Claude Fable 5.1',
}

const capitalize = (word: string) => word.charAt(0).toUpperCase() + word.slice(1)

/** Display names for model ids: "gpt-4o-mini-tts" -> "GPT-4o mini TTS", "aura-2-asteria-en" -> "Aura-2 Asteria". */
export function prettyModel(id: string): string {
  if (MODEL_NAMES[id]) return MODEL_NAMES[id]
  const name = id.includes('/') ? id.split('/').pop()! : id
  let match: RegExpMatchArray | null
  if (name.startsWith('gpt-')) {
    return name.replace('gpt-', 'GPT-').replace(/-(mini|nano)(?=-|$)/, ' $1').replace(/-tts$/, ' TTS')
  }
  if ((match = name.match(/^eleven_([a-z]+)_v(\d+)(?:_(\d+))?$/))) {
    return `Eleven ${capitalize(match[1])} v${match[2]}${match[3] ? `.${match[3]}` : ''}`
  }
  if ((match = name.match(/^aura-(\d+)-([a-z]+)-[a-z]{2}$/))) return `Aura-${match[1]} ${capitalize(match[2])}`
  if ((match = name.match(/^gemini-([\d.]+)-(.+)$/))) {
    return `Gemini ${match[1]} ${match[2].split('-').map(capitalize).join(' ')}`
  }
  return capitalize(name)
}

const VENDOR_NAMES: Record<string, string> = {
  openai: 'OpenAI',
  elevenlabs: 'ElevenLabs',
  deepgram: 'Deepgram',
  google: 'Google',
  anthropic: 'Anthropic',
  cartesia: 'Cartesia',
  livekit: 'LiveKit Inference',
}

/** "deepgram/nova-3" -> "Deepgram", "openai" -> "OpenAI". */
export function prettyVendor(id: string): string {
  const vendor = id.split('/')[0]
  return VENDOR_NAMES[vendor] ?? vendor.charAt(0).toUpperCase() + vendor.slice(1)
}
