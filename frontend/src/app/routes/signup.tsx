import { useGoogleLogin } from '@react-oauth/google'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate } from 'react-router'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/contexts/auth-context'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import { Form, FormControl, FormField, FormItem } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { authService } from '@/services/auth.service'
import { useAppDispatch } from '@/state/store'
import { setUser } from '@/state/slice/user'
import { fetchWishlist } from '@/state/slice/favorites'
import { storeAccessToken } from '@/utils/auth-token'

const isTauri = !!(window as unknown as { __TAURI_INTERNALS__: unknown })
    .__TAURI_INTERNALS__

const FormSchema = z.object({
    name: z.string({ error: 'Name is required' }).min(1, {
        message: 'Name is required'
    }),
    email: z.email({ error: 'Invalid email address' }),
    password: z.string({ error: 'Password is required' }).min(6, {
        message: 'Password must be at least 6 characters'
    })
})

type AuthPayload = {
    access_token: string
    refresh_token?: string
    token_type?: string
    expires_in?: number
}

export function SignupPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const { loginWithAuthCode } = useAuth()
    const dispatch = useAppDispatch()
    const authHandledRef = useRef(false)

    const form = useForm<z.infer<typeof FormSchema>>({
        resolver: zodResolver(FormSchema),
        defaultValues: {
            name: '',
            email: '',
            password: ''
        }
    })

    const googleLogin = useGoogleLogin({
        flow: 'auth-code',
        onSuccess: async (codeResponse) => {
            try {
                await loginWithAuthCode(codeResponse.code)
                navigate('/')
            } catch (error) {
                console.error('Failed to login with auth code:', error)
            }
        },
        onError: (errorResponse) => {
            console.log('Login Failed:', errorResponse)
        }
    })

    const apiBaseUrl = useMemo(
        () => import.meta.env.VITE_API_URL || 'http://localhost:8000',
        []
    )

    const handleAuthSuccess = useCallback(
        async (payload: AuthPayload | null | undefined) => {
            if (!payload || typeof payload.access_token !== 'string') {
                authHandledRef.current = false
                return
            }
            if (authHandledRef.current) return
            authHandledRef.current = true

            try {
                storeAccessToken(payload.access_token)
                const userRes = await authService.getCurrentUser()
                dispatch(setUser(userRes))
                dispatch(fetchWishlist())
                navigate('/')
            } catch (error) {
                console.error('Failed to finalize Google login:', error)
                authHandledRef.current = false
            }
        },
        [dispatch, navigate]
    )

    const apiOrigin = useMemo(() => {
        try {
            return new URL(apiBaseUrl).origin
        } catch {
            return apiBaseUrl
        }
    }, [apiBaseUrl])

    useEffect(() => {
        const handler = (event: MessageEvent) => {
            if (event.origin !== apiOrigin) return
            const data = event.data as {
                type?: string
                payload?: AuthPayload
            }
            if (!data || data.type !== 'google-auth-success') return
            void handleAuthSuccess(data.payload)
        }
        window.addEventListener('message', handler)
        return () => window.removeEventListener('message', handler)
    }, [apiOrigin, handleAuthSuccess])

    const loginWithGoogleDesktop = useCallback(async () => {
        authHandledRef.current = false

        const state = crypto.randomUUID()
        const frontendOrigin =
            import.meta.env.VITE_FRONTEND_URL || 'http://localhost:1420'
        const url = `${frontendOrigin}/login?desktop_state=${state}`

        const { open } = await import('@tauri-apps/plugin-shell')
        await open(url)

        const poll = setInterval(async () => {
            try {
                const token = await authService.pollDesktopToken(state)
                if (!token) return
                clearInterval(poll)
                void handleAuthSuccess(token)
            } catch {
                // keep polling
            }
        }, 2000)
        setTimeout(() => clearInterval(poll), 5 * 60 * 1000)
    }, [handleAuthSuccess])

    const onSubmit = async (data: z.infer<typeof FormSchema>) => {
        console.log(data)
    }

    return (
        <div className="flex flex-col items-center justify-center w-full h-full">
            <h1 className="text-[32px] font-semibold text-firefly dark:text-sky-blue">
                Welcome to II-Agent
            </h1>
            <p className="text-[28px] text-firefly dark:text-sky-blue mb-12">
                Helping you with your task today
            </p>

            <div className="flex flex-col w-full justify-center max-w-[510px]">
                <Form {...form}>
                    <form
                        onSubmit={form.handleSubmit(onSubmit)}
                        className="flex flex-col gap-10"
                    >
                        <div className="space-y-6">
                            <FormField
                                control={form.control}
                                name="name"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormControl>
                                            <div className="space-y-2 relative">
                                                <Icon
                                                    name="user"
                                                    className="absolute top-3 left-4 fill-black dark:fill-white"
                                                />
                                                <Input
                                                    id="name"
                                                    className="pl-[56px]"
                                                    type="text"
                                                    placeholder="Enter your name"
                                                    {...field}
                                                />
                                            </div>
                                        </FormControl>
                                    </FormItem>
                                )}
                            />
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
                        </div>
                        <div className="w-full flex justify-center">
                            <Button
                                type="submit"
                                size="xl"
                                className=" bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-black font-semibold w-full max-w-[247px]"
                                disabled={!form.formState.isValid}
                            >
                                Sign up
                            </Button>
                        </div>
                    </form>
                </Form>
                <div className="flex justify-center items-center gap-2 text-black dark:text-white text-sm mt-8">
                    <span>Already have an account?</span>
                    <Link
                        to="/login"
                        className="text-black dark:text-white text-sm font-semibold"
                    >
                        Sign in
                    </Link>
                </div>
                <div className="flex w-full items-center gap-4 my-10">
                    <p className="flex-1 bg-black/[0.31] dark:bg-white/[0.31] h-[1px]"></p>
                    <span className="text-sm text-black dark:text-white font-semibold">
                        {t('common.or')}
                    </span>
                    <p className="flex-1 bg-black/[0.31] dark:bg-white/[0.31] h-[1px]"></p>
                </div>
                <p className="text-xs text-center text-firefly/70 dark:text-sky-blue/70 mb-6">
                    {t('auth.privacyNotice')}{' '}
                    <a
                        href="/privacy"
                        className="underline hover:text-firefly dark:hover:text-sky-blue"
                    >
                        {t('auth.privacyNoticeLink')}
                    </a>
                </p>
                <Button
                    size="xl"
                    onClick={() =>
                        isTauri ? loginWithGoogleDesktop() : googleLogin()
                    }
                    className="w-full bg-white text-black font-semibold shadow-btn"
                >
                    <Icon name="google" className="size-[22px]" />
                    {t('auth.continueWithGoogle')}
                </Button>
            </div>
        </div>
    )
}

export const Component = SignupPage
