import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { ACCESS_TOKEN } from '@/constants/auth'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/auth-context'

type Status = 'loading' | 'needs-consent' | 'sending' | 'done' | 'error'

const EXTENSION_MESSAGE_TYPE = 'ii-extension-auth'

export function ExtensionAuthPage() {
    const [searchParams] = useSearchParams()
    const { user, isAuthenticated, isLoading } = useAuth()
    const [status, setStatus] = useState<Status>('loading')
    const [error, setError] = useState<string | null>(null)

    const extId = searchParams.get('ext_id') || ''
    const nonce = searchParams.get('nonce') || ''
    const browserVendor = searchParams.get('browser') || ''

    // The extension sends its own origin so the frontend can postMessage back
    // specifically to the extension context listening in a content script.
    // We keep it opaque (the extension is responsible for scoping).
    const returnUrl = useMemo(() => {
        // Extensions in Chromium use chrome-extension://<id>/... in `window.location.href`
        // but the extension's content script injected into THIS page will listen
        // on window.postMessage, so we always postMessage to our own origin.
        return window.location.origin
    }, [])

    const postTokenToExtension = useCallback(
        (token: string) => {
            // postMessage bounces through a content script the extension injects
            // into this frontend origin. Both the content script and this page
            // are same-origin, so `window.postMessage` with targetOrigin=own
            // origin is the safe path. The content script verifies the nonce
            // matches what the extension sent, then relays to the background.
            window.postMessage(
                {
                    type: EXTENSION_MESSAGE_TYPE,
                    nonce,
                    ext_id: extId,
                    payload: {
                        access_token: token,
                        token_type: 'bearer',
                    },
                },
                returnUrl,
            )
        },
        [nonce, extId, returnUrl],
    )

    // Validate required params.
    useEffect(() => {
        if (!extId || !nonce) {
            setError(
                'Missing extension parameters. Please start the sign-in again from the extension.',
            )
            setStatus('error')
        }
    }, [extId, nonce])

    // Redirect to login if not authenticated.
    useEffect(() => {
        if (status === 'error') return
        if (isLoading) return
        if (isAuthenticated) {
            setStatus('needs-consent')
            return
        }

        const here = `${window.location.pathname}${window.location.search}`
        const loginUrl = `/login?return_to=${encodeURIComponent(here)}`
        window.location.replace(loginUrl)
    }, [isLoading, isAuthenticated, status])

    const handleAllow = useCallback(() => {
        const token = localStorage.getItem(ACCESS_TOKEN)
        if (!token) {
            setError('No access token found in this browser. Please sign in again.')
            setStatus('error')
            return
        }

        setStatus('sending')
        postTokenToExtension(token)

        // Poll for the extension's ack so the user sees "Done" after the
        // content script confirms delivery. If no ack in 2s, still show done —
        // the extension content script is responsible for closing this tab.
        const timer = window.setTimeout(() => setStatus('done'), 1500)
        const onAck = (event: MessageEvent) => {
            if (event.origin !== window.location.origin) return
            const data = event.data as { type?: string; nonce?: string }
            if (data?.type !== 'ii-extension-auth-ack' || data?.nonce !== nonce) return
            window.clearTimeout(timer)
            window.removeEventListener('message', onAck)
            setStatus('done')
        }
        window.addEventListener('message', onAck)
    }, [postTokenToExtension, nonce])

    const handleDeny = useCallback(() => {
        window.postMessage(
            { type: `${EXTENSION_MESSAGE_TYPE}-denied`, nonce, ext_id: extId },
            returnUrl,
        )
        window.setTimeout(() => window.close(), 300)
    }, [nonce, extId, returnUrl])

    if (status === 'loading' || isLoading) {
        return <CenterBox><Spinner /></CenterBox>
    }

    if (status === 'error') {
        return (
            <CenterBox>
                <h1 className="text-xl font-semibold mb-2">Sign-in error</h1>
                <p className="text-sm text-pewter dark:text-grey-4">{error}</p>
            </CenterBox>
        )
    }

    if (status === 'done') {
        return (
            <CenterBox>
                <h1 className="text-xl font-semibold mb-2">You can close this tab</h1>
                <p className="text-sm text-pewter dark:text-grey-4">
                    The II-Agent extension is now signed in.
                </p>
            </CenterBox>
        )
    }

    const displayName = user?.first_name
        ? `${user.first_name} ${user.last_name ?? ''}`.trim()
        : user?.email || 'your account'

    return (
        <div className="flex items-center justify-center min-h-screen px-4">
            <div className="bg-white dark:bg-firefly rounded-2xl shadow-xl p-8 max-w-md w-full">
                <div className="flex items-center justify-center gap-4 mb-8">
                    <img
                        src="/images/logo-only.png"
                        alt="II-Agent"
                        className="size-12 rounded-xl"
                    />
                    <span className="text-gray-400 text-2xl">···</span>
                    <div className="size-12 rounded-xl bg-sky-blue-4/20 dark:bg-sky-blue/10 flex items-center justify-center">
                        <span className="text-2xl">🧩</span>
                    </div>
                </div>

                <h1 className="text-xl font-semibold text-center text-gray-900 dark:text-white mb-2">
                    Allow the II-Agent {browserVendor ? browserVendor : 'browser'} extension to sign in?
                </h1>

                <p className="text-center text-pewter dark:text-grey-4 mb-6">
                    Signed in as <span className="font-medium">{displayName}</span>
                </p>

                <div className="mb-6 space-y-2">
                    <Line text="Use the extension as your signed-in account" />
                    <Line text="Access chat sessions you create in the extension" />
                    <Line text="You can sign out from the extension at any time" />
                </div>

                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        className="flex-1"
                        onClick={handleDeny}
                        disabled={status === 'sending'}
                    >
                        Deny
                    </Button>
                    <Button
                        className="flex-1 bg-sky-blue text-black"
                        onClick={handleAllow}
                        disabled={status === 'sending'}
                    >
                        {status === 'sending' ? 'Sending…' : 'Allow'}
                    </Button>
                </div>

                <p className="text-[11px] text-center text-pewter dark:text-grey-4 mt-6">
                    The extension ID requesting access is{' '}
                    <code className="font-mono break-all">{extId}</code>.
                </p>
            </div>
        </div>
    )
}

function CenterBox({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex items-center justify-center min-h-screen px-4 text-center">
            <div className="max-w-md">{children}</div>
        </div>
    )
}

function Spinner() {
    return (
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white mx-auto" />
    )
}

function Line({ text }: { text: string }) {
    return (
        <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
            <span className="text-green-500">✓</span>
            <span>{text}</span>
        </div>
    )
}

export const Component = ExtensionAuthPage
