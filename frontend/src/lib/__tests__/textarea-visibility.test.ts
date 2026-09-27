import { describe, expect, it } from 'vitest'

import {
    getComposerBottomInset,
    keepTextareaTailVisible,
    shouldKeepTextareaTailVisible
} from '../textarea-visibility'

describe('textarea visibility helpers', () => {
    it('keeps a safe bottom inset for the composer footer', () => {
        expect(getComposerBottomInset(0, false)).toBe(72)
        expect(getComposerBottomInset(40, false)).toBe(72)
        expect(getComposerBottomInset(80, true)).toBe(92)
    })

    it('detects when the cursor is on the last visible line', () => {
        expect(shouldKeepTextareaTailVisible('one\ntwo', 7)).toBe(true)
        expect(shouldKeepTextareaTailVisible('one\ntwo\nthree', 2)).toBe(false)
    })

    it('scrolls the textarea to keep the tail visible while typing', () => {
        const textarea = {
            value: 'first line\nsecond line',
            selectionStart: 'first line\nsecond line'.length,
            scrollHeight: 240,
            scrollTop: 0
        }

        keepTextareaTailVisible(textarea)

        expect(textarea.scrollTop).toBe(240)
    })
})
