import { useGoogleLogin } from '@react-oauth/google'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'

interface GoogleSignInButtonProps {
    onLoginSuccess: (code: string) => Promise<void>
    onLoginError?: () => void
}

/**
 * Google sign-in button component.
 *
 * IMPORTANT: This component is isolated in its own file to prevent
 * @react-oauth/google from being imported when Google auth is disabled.
 * The useGoogleLogin hook requires GoogleOAuthProvider context, which
 * is only rendered when:
 *   - VITE_GOOGLE_CLIENT_ID is set, AND
 *   - VITE_DEV_AUTH_AUTOLOGIN is not 'true'
 *
 * Only import/render this component when Google auth is enabled.
 */
export function GoogleSignInButton({
    onLoginSuccess,
    onLoginError
}: GoogleSignInButtonProps) {
    const googleLogin = useGoogleLogin({
        flow: 'auth-code',
        onSuccess: async (codeResponse) => {
            await onLoginSuccess(codeResponse.code)
        },
        onError: onLoginError || (() => console.log('Google Login Failed'))
    })

    return (
        <Button
            size="xl"
            onClick={() => googleLogin()}
            className="w-full bg-white text-black font-semibold shadow-btn"
        >
            <Icon name="google" className="size-[22px]" />
            Continue with Google Account
        </Button>
    )
}
