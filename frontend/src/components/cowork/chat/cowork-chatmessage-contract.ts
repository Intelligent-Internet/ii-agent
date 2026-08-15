export type CoworkTranscriptMessageKind = 'thinking' | 'response'

const normalizeCoworkTranscriptAnchor = (anchor: string) =>
    anchor.replace(/\s+/g, '-').trim()

export const buildCoworkTranscriptMessageId = (
    kind: CoworkTranscriptMessageKind,
    anchor: string
) => `cowork-transcript:${kind}:${normalizeCoworkTranscriptAnchor(anchor)}`

export const resolveCoworkTranscriptAnchor = (
    ...candidates: Array<string | null | undefined>
) => candidates.find((candidate) => typeof candidate === 'string' && candidate.trim())
