import { useEffect } from 'react'

import {
    setCurrentQuestion,
    setEditingMessage,
    setLoading,
    setMessages,
    setRunStatus,
    setWorkspaceInfo,
    useAppDispatch
} from '@/state'
import type { ChatMessageAdapterState } from './chat-message-adapter-contract'

export const useChatMessageAdapterState = ({
    messages,
    runStatus,
    isLoading,
    workspaceInfo,
    resetEditingOnKey,
    clearCurrentQuestionOnCleanup = true
}: ChatMessageAdapterState) => {
    const dispatch = useAppDispatch()

    useEffect(() => {
        dispatch(setMessages(messages))
    }, [dispatch, messages])

    useEffect(() => {
        dispatch(setRunStatus(runStatus))
    }, [dispatch, runStatus])

    useEffect(() => {
        dispatch(setLoading(isLoading))
    }, [dispatch, isLoading])

    useEffect(() => {
        if (workspaceInfo === undefined) {
            return
        }

        dispatch(setWorkspaceInfo(workspaceInfo))
    }, [dispatch, workspaceInfo])

    useEffect(() => {
        if (resetEditingOnKey === undefined) {
            return
        }

        dispatch(setEditingMessage(undefined))
    }, [dispatch, resetEditingOnKey])

    useEffect(() => {
        return () => {
            dispatch(setMessages([]))
            dispatch(setRunStatus(null))
            dispatch(setLoading(false))
            if (clearCurrentQuestionOnCleanup) {
                dispatch(setCurrentQuestion(''))
            }
            dispatch(setEditingMessage(undefined))
        }
    }, [clearCurrentQuestionOnCleanup, dispatch])
}
