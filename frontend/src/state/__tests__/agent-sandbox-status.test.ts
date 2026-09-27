import { describe, expect, it } from 'vitest'
import {
    agentReducer,
    setSandboxStatus,
    selectSandboxStatus
} from '../../state/slice/agent'

describe('agentSlice – sandboxStatus', () => {
    const initialState = agentReducer(undefined, { type: '@@INIT' })

    it('has empty string as initial sandboxStatus', () => {
        expect(initialState.sandboxStatus).toBe('')
    })

    it('setSandboxStatus sets the value', () => {
        const state = agentReducer(initialState, setSandboxStatus('running'))
        expect(state.sandboxStatus).toBe('running')
    })

    it('setSandboxStatus can set to paused', () => {
        const state = agentReducer(initialState, setSandboxStatus('paused'))
        expect(state.sandboxStatus).toBe('paused')
    })

    it('setSandboxStatus can reset to empty', () => {
        const running = agentReducer(initialState, setSandboxStatus('running'))
        const reset = agentReducer(running, setSandboxStatus(''))
        expect(reset.sandboxStatus).toBe('')
    })

    it('selectSandboxStatus reads from state', () => {
        const state = { agent: agentReducer(initialState, setSandboxStatus('running')) }
        expect(selectSandboxStatus(state)).toBe('running')
    })
})
