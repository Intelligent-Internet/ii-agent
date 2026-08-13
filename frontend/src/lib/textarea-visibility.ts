export const getComposerBottomInset = (
    footerHeight: number,
    isMobile: boolean
): number => Math.max(footerHeight + 12, isMobile ? 80 : 72)

export const shouldKeepTextareaTailVisible = (
    value: string,
    selectionStart: number | null | undefined
): boolean => {
    const cursorPosition = selectionStart ?? value.length
    return !value.substring(cursorPosition).includes('\n')
}

type TailVisibleTextarea = Pick<
    HTMLTextAreaElement,
    'value' | 'selectionStart' | 'scrollHeight' | 'scrollTop'
>

const revealInScrollableAncestors = (
    element: HTMLTextAreaElement,
    bottomOffset: number
): void => {
    const elementRect = element.getBoundingClientRect()

    let parent = element.parentElement
    while (parent) {
        const style = window.getComputedStyle(parent)
        const isScrollable =
            /(auto|scroll)/.test(style.overflowY) ||
            /(auto|scroll)/.test(style.overflow)

        if (isScrollable) {
            const parentRect = parent.getBoundingClientRect()
            const overflowAmount =
                elementRect.bottom + bottomOffset - parentRect.bottom

            if (overflowAmount > 0) {
                parent.scrollTop += overflowAmount + 8
            }
        }

        parent = parent.parentElement
    }

    const viewportOverflow =
        elementRect.bottom + bottomOffset - window.innerHeight

    if (viewportOverflow > 0) {
        window.scrollBy({
            top: viewportOverflow + 8,
            behavior: 'instant'
        })
    }
}

export const keepTextareaTailVisible = (
    textarea: HTMLTextAreaElement | TailVisibleTextarea | null,
    bottomOffset = 0
): void => {
    if (!textarea) return

    if (shouldKeepTextareaTailVisible(textarea.value, textarea.selectionStart)) {
        textarea.scrollTop = textarea.scrollHeight

        if (textarea instanceof HTMLTextAreaElement) {
            revealInScrollableAncestors(textarea, bottomOffset)
        }
    }
}
