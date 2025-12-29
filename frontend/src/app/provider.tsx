import { ReactNode, Suspense } from 'react'
import { ThemeProvider } from 'next-themes'
import { GoogleOAuthProvider } from '@react-oauth/google'
import AppErrorPage from '@/features/errors/app-error'
import { ErrorBoundary } from 'react-error-boundary'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TerminalProvider } from '@/contexts/terminal-context'
import { AuthProvider } from '@/contexts/auth-context'

// Check if dev auth auto-login is enabled (skip Google auth in this case)
const DEV_AUTH_AUTOLOGIN = import.meta.env.VITE_DEV_AUTH_AUTOLOGIN === 'true'
// Google client ID from env (may be empty/undefined/whitespace)
// Trim whitespace to avoid treating whitespace-only values as valid
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim()

// Only initialize Google auth if:
// 1. Dev auto-login is NOT enabled, AND
// 2. A valid (non-empty, non-whitespace) Google client ID is provided
const shouldEnableGoogleAuth = !DEV_AUTH_AUTOLOGIN && googleClientId

if (DEV_AUTH_AUTOLOGIN) {
    console.info('[auth] Google auth disabled: VITE_DEV_AUTH_AUTOLOGIN is enabled')
} else if (!googleClientId) {
    console.info('[auth] Google auth disabled: missing or empty VITE_GOOGLE_CLIENT_ID')
} else {
    console.info('[auth] Google auth enabled with client_id:', googleClientId.slice(0, 10) + '...')
}

// Wrapper component that conditionally includes GoogleOAuthProvider
function AuthWrapper({ children }: { children: ReactNode }) {
    if (!shouldEnableGoogleAuth) {
        return <>{children}</>
    }
    return <GoogleOAuthProvider clientId={googleClientId}>{children}</GoogleOAuthProvider>
}

export default function AppProvider({ children }: { children: ReactNode }) {
    return (
        <Suspense fallback={<>Loading...</>}>
            <ErrorBoundary FallbackComponent={AppErrorPage}>
                <AuthWrapper>
                    <AuthProvider>
                        <ThemeProvider
                            attribute="class"
                            defaultTheme="dark"
                            enableSystem
                        >
                            <TerminalProvider>
                                <TooltipProvider>{children}</TooltipProvider>
                            </TerminalProvider>
                        </ThemeProvider>
                    </AuthProvider>
                </AuthWrapper>
            </ErrorBoundary>
        </Suspense>
    )
}
