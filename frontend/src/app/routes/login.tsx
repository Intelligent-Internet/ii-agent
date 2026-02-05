import { useGoogleLogin } from '@react-oauth/google'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate } from 'react-router'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'

import { useAuth } from '@/contexts/auth-context'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import { Form, FormControl, FormField, FormItem } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { ACCESS_TOKEN } from '@/constants/auth'
import { authService } from '@/services/auth.service'
import { useAppDispatch } from '@/state/store'
import { setUser } from '@/state/slice/user'
import { fetchWishlist } from '@/state/slice/favorites'
import { toast } from 'sonner'

const FormSchema = z.object({
    email: z.email({ error: 'Invalid email address' }),
    password: z.string({ error: 'Password is required' }).min(6, {
        message: 'Password must be at least 6 characters'
    })
})

type IiAuthPayload = {
    access_token: string
    refresh_token?: string
    token_type?: string
    expires_in?: number
}

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

// Separate component for Google login button to safely use the hook
function GoogleLoginButton({ onSuccess, onError }: {
    onSuccess: (code: string) => Promise<void>,
    onError: (error: unknown) => void
}) {
    const googleLogin = useGoogleLogin({
        flow: 'auth-code',
        onSuccess: async (codeResponse) => {
            await onSuccess(codeResponse.code)
        },
        onError: onError
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

export function LoginPage() {
    const navigate = useNavigate()
    const { loginWithAuthCode, loginWithPassword } = useAuth()
    const dispatch = useAppDispatch()

    const form = useForm<z.infer<typeof FormSchema>>({
        resolver: zodResolver(FormSchema),
        defaultValues: {
            email: '',
            password: ''
        }
    })

    const handleGoogleSuccess = useCallback(async (code: string) => {
        try {
            await loginWithAuthCode(code)
            navigate('/')
        } catch (error: unknown) {
            const apiError = error as {
                response: { data: { detail: string } }
            }
            const errorMessage =
                typeof apiError?.response?.data?.detail === 'string'
                    ? apiError.response.data.detail
                    : 'Login failed. Please try again.'
            if (errorMessage?.includes('beta')) {
                toast.info(errorMessage)
            } else {
                toast.error(errorMessage)
            }
        }
    }, [loginWithAuthCode, navigate])

    const handleGoogleError = useCallback((errorResponse: unknown) => {
        console.log('Login Failed:', errorResponse)
    }, [])

    const apiBaseUrl = useMemo(
        () => import.meta.env.VITE_API_URL || 'http://localhost:8000',
        []
    )
    const apiOrigin = useMemo(() => {
        try {
            return new URL(apiBaseUrl).origin
        } catch (error) {
            console.error('Invalid API base URL:', error)
            return apiBaseUrl
        }
    }, [apiBaseUrl])

    const authHandledRef = useRef(false)

    const handleAuthSuccess = useCallback(
        async (payload: IiAuthPayload | null | undefined) => {
            if (!payload || typeof payload.access_token !== 'string') {
                authHandledRef.current = false
                return
            }

            if (authHandledRef.current) {
                return
            }
            authHandledRef.current = true

            try {
                localStorage.setItem(ACCESS_TOKEN, payload.access_token)
                window.dispatchEvent(new CustomEvent('auth-token-set'))

                const userRes = await authService.getCurrentUser()
                dispatch(setUser(userRes))
                dispatch(fetchWishlist())

                navigate('/')
            } catch (error) {
                console.error('Failed to finalize II login:', error)
                authHandledRef.current = false
            }
        },
        [dispatch, navigate]
    )

    useEffect(() => {
        const handler = (event: MessageEvent) => {
            if (event.origin !== apiOrigin) {
                return
            }

            const data = event.data as {
                type?: string
                payload?: IiAuthPayload
            }

            if (!data || data.type !== 'ii-auth-success') {
                return
            }

            void handleAuthSuccess(data.payload)
        }

        window.addEventListener('message', handler)
        return () => window.removeEventListener('message', handler)
    }, [apiOrigin, handleAuthSuccess])

    useEffect(() => {
        const hash = window.location.hash
        if (!hash || !hash.includes('ii-auth=')) {
            return
        }

        const params = new URLSearchParams(hash.slice(1))
        const encoded = params.get('ii-auth')
        params.delete('ii-auth')

        const cleanHash = params.toString()
        const cleanUrl = `${window.location.pathname}${window.location.search}${cleanHash ? `#${cleanHash}` : ''}`
        window.history.replaceState(null, '', cleanUrl)

        if (!encoded) {
            return
        }

        try {
            const payload = JSON.parse(
                decodeURIComponent(encoded)
            ) as IiAuthPayload
            void handleAuthSuccess(payload)
        } catch (error) {
            console.error('Failed to parse II auth payload from hash:', error)
            authHandledRef.current = false
        }
    }, [handleAuthSuccess])

    const loginWithII = useCallback(() => {
        authHandledRef.current = false

        const url = new URL('/auth/oauth/ii/login', apiBaseUrl)
        url.searchParams.set('return_to', window.location.href)

        const width = 500
        const height = 700
        const left = window.screenX + (window.outerWidth - width) / 2
        const top = window.screenY + (window.outerHeight - height) / 2

        const features = [
            `width=${Math.max(400, Math.floor(width))}`,
            `height=${Math.max(500, Math.floor(height))}`,
            `left=${Math.max(0, Math.floor(left))}`,
            `top=${Math.max(0, Math.floor(top))}`,
            'resizable=yes',
            'scrollbars=yes'
        ].join(',')

        const popup = window.open(url.toString(), 'ii-login', features)

        if (!popup) {
            window.location.href = url.toString()
            return
        }

        popup.focus()
    }, [apiBaseUrl])

    const onSubmit = async (data: z.infer<typeof FormSchema>) => {
        try {
            await loginWithPassword(data.email, data.password)
            navigate('/')
        } catch (error: unknown) {
            const apiError = error as {
                response?: { data?: { detail?: string } }
            }
            const errorMessage =
                typeof apiError?.response?.data?.detail === 'string'
                    ? apiError.response.data.detail
                    : 'Login failed. Please try again.'
            toast.error(errorMessage)
        }
    }

    const hideSigninWithPassword = false

    return (
        <div className="flex flex-col items-center justify-center w-full h-full">
            <h1 className="text-[25px] md:text-[32px] font-semibold dark:text-sky-blue">
                Welcome to II-Agent
            </h1>
            <p className="text-[20px] md:text-[28px] dark:text-sky-blue mb-12">
                Helping you with your task today
            </p>

            <div className="flex flex-col w-full justify-center max-w-[510px]">
                <div className={`${hideSigninWithPassword ? 'hidden' : ''}`}>
                    <Form {...form}>
                        <form
                            onSubmit={form.handleSubmit(onSubmit)}
                            className="flex flex-col gap-10"
                        >
                            <div className="space-y-6">
                                <FormField
                                    control={form.control}
                                    name="email"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="email"
                                                        className="absolute top-3 left-4 fill-black dark:fill-white"
                                                    />
                                                    <Input
                                                        id="email"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder="Enter your email address"
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                                <div className="space-y-4 text-right">
                                    <FormField
                                        control={form.control}
                                        name="password"
                                        render={({ field }) => (
                                            <FormItem>
                                                <FormControl>
                                                    <div className="space-y-2 relative">
                                                        <Icon
                                                            name="key"
                                                            className="absolute top-3 left-4 fill-black dark:fill-white"
                                                        />
                                                        <Input
                                                            id="password"
                                                            className="pl-[56px]"
                                                            type="password"
                                                            placeholder="Enter your password"
                                                            {...field}
                                                        />
                                                    </div>
                                                </FormControl>
                                            </FormItem>
                                        )}
                                    />
                                    <Link
                                        to="/forgot-password"
                                        className="text-sm underline"
                                    >
                                        Forgot your password?
                                    </Link>
                                </div>
                            </div>
                            <div className="w-full flex justify-center">
                                <Button
                                    type="submit"
                                    size="xl"
                                    className="bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-black font-semibold w-full max-w-[247px]"
                                    disabled={!form.formState.isValid}
                                >
                                    Sign in
                                </Button>
                            </div>
                        </form>
                    </Form>
                    <div className="flex justify-center items-center gap-2 dark:text-white text-sm mt-8">
                        <span>You don&apos;t have account yet?</span>
                        <Link
                            to="/signup"
                            className="dark:text-white text-sm font-semibold"
                        >
                            Sign up
                        </Link>
                    </div>
                    <div className="flex w-full items-center gap-4 my-10">
                        <p className="flex-1 dark:bg-white/[0.31] h-[1px]"></p>
                        <span className="text-sm dark:text-white font-semibold">
                            OR
                        </span>
                        <p className="flex-1 dark:bg-white/[0.31] h-[1px]"></p>
                    </div>
                </div>
                {googleClientId && (
                    <GoogleLoginButton
                        onSuccess={handleGoogleSuccess}
                        onError={handleGoogleError}
                    />
                )}
                <Button
                    size="xl"
                    onClick={loginWithII}
                    className="w-full mt-4 md:mt-10 bg-white text-black font-semibold shadow-btn"
                >
                    <img
                        src="/images/logo-charcoal.png"
                        alt="logo"
                        className="size-[22px]"
                    />
                    Continue with II Account
                </Button>
            </div>
        </div>
    )
}

export const Component = LoginPage
