import { QUESTION_MODE } from '@/typings/agent'

type QuestionModeValue = QUESTION_MODE | string | null | undefined

export const COWORK_ROUTE = '/cowork'

const normalizeQuestionMode = (
    mode: QuestionModeValue
): QUESTION_MODE | null => {
    switch (mode) {
        case QUESTION_MODE.CHAT:
            return QUESTION_MODE.CHAT
        case QUESTION_MODE.COWORK:
            return QUESTION_MODE.COWORK
        case QUESTION_MODE.AGENT:
            return QUESTION_MODE.AGENT
        default:
            return null
    }
}

export const isAgenticQuestionMode = (
    mode: QuestionModeValue
): mode is QUESTION_MODE.AGENT =>
    normalizeQuestionMode(mode) === QUESTION_MODE.AGENT

export const isCoworkQuestionMode = (
    mode: QuestionModeValue
): mode is QUESTION_MODE.COWORK =>
    normalizeQuestionMode(mode) === QUESTION_MODE.COWORK

interface SessionRouteOptions {
    sessionId: string
    agentType?: string | null
}

export const getSessionRoute = ({
    sessionId,
    agentType
}: SessionRouteOptions) => {
    if (agentType === 'chat') {
        return `/chat?id=${sessionId}`
    }

    return `/${sessionId}`
}
