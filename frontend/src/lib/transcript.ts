import { useTranscriptions } from '@livekit/components-react'
import type { Room } from 'livekit-client'
import { useMemo, useState } from 'react'

export interface TypedMessage {
  id: string
  text: string
  at: number
}

export interface TranscriptEntry {
  id: string
  speaker: 'nova' | 'you'
  text: string
  /** Place in the conversation: lines are numbered as their first words appear. */
  order: number
  typed?: boolean
  final: boolean
}

interface Lines {
  entries: Record<string, TranscriptEntry>
  next: number
}

/**
 * Spoken lines (LiveKit transcription streams) merged with questions typed in the box.
 * Lines are kept after the room disconnects, so the summary can still offer the transcript.
 */
export function useTranscriptEntries(room: Room, typed: TypedMessage[]): TranscriptEntry[] {
  const streams = useTranscriptions({ room })
  const [lines, setLines] = useState<Lines>({ entries: {}, next: 1 })
  const [seen, setSeen] = useState({ streams, typed })

  // Fold new stream updates and typed questions into the kept lines (state adjusted during
  // render, so no extra effect pass). Streams that vanish on disconnect are simply not removed.
  if (streams !== seen.streams || typed !== seen.typed) {
    setSeen({ streams, typed })
    const entries = { ...lines.entries }
    let next = lines.next
    for (const stream of streams) {
      // Interim and final versions of one utterance arrive as separate streams that share
      // a segment id; keying by it keeps one line that updates in place.
      const id = stream.streamInfo.attributes?.['lk.segment_id'] ?? stream.streamInfo.id
      entries[id] = {
        id,
        speaker: stream.participantInfo.identity === room.localParticipant.identity ? 'you' : 'nova',
        text: stream.text,
        // Numbered when its first words appear, not by the stream's own timestamp: a stream
        // can open before it has words, which put a question above the greeting it interrupted.
        order: entries[id]?.order || (stream.text.trim() ? next++ : 0),
        final: stream.streamInfo.attributes?.['lk.transcription_final'] === 'true',
      }
    }
    for (const message of typed) {
      entries[message.id] ??= { id: message.id, speaker: 'you', text: message.text, order: next++, typed: true, final: true }
    }
    setLines({ entries, next })
  }

  return useMemo(() => {
    const ordered = Object.values(lines.entries)
      .filter((entry) => entry.order && entry.text.trim())
      .sort((a, b) => a.order - b.order)
    // Speech-to-text can split one spoken question into pieces at a pause; show them as one line.
    const merged: TranscriptEntry[] = []
    for (const entry of ordered) {
      const previous = merged.at(-1)
      if (previous && previous.speaker === 'you' && entry.speaker === 'you' && !previous.typed && !entry.typed) {
        merged[merged.length - 1] = { ...previous, text: `${previous.text} ${entry.text}`, final: entry.final }
      } else {
        merged.push(entry)
      }
    }
    return merged
  }, [lines])
}
