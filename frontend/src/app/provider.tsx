import { ReactNode, Suspense } from 'react'
import { ThemeProvider } from 'next-themes'
import { GoogleOAuthProvider } from '@react-oauth/google'
import AppErrorPage from '@/features/errors/app-error'
import { ErrorBoundary } from 'react-error-boundary'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TerminalProvider } from '@/contexts/terminal-context'
import { AuthProvider } from '@/contexts/auth-context'

export default function AppProvider({ children }: { children: ReactNode }) {
    const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

    const content = (
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
    )

    return (
        <Suspense fallback={<>Loading...</>}>
            <ErrorBoundary FallbackComponent={AppErrorPage}>
                {googleClientId ? (
                    <GoogleOAuthProvider clientId={googleClientId}>
                        {content}
                    </GoogleOAuthProvider>
                ) : (
                    content
                )}
            </ErrorBoundary>
        </Suspense>
    )
}
