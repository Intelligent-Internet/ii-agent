import { useGoogleLogin } from '@react-oauth/google'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
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
import { fetchPins } from '@/state/slice/pins'
import { toast } from 'sonner'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { storeAccessToken } from '@/utils/auth-token'

const isTauri = !!(window as unknown as { __TAURI_INTERNALS__: unknown })
    .__TAURI_INTERNALS__

type IiAuthPayload = {
    access_token: string
    refresh_token?: string
    token_type?: string
    expires_in?: number
}

export function LoginPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const { loginWithAuthCode } = useAuth()
    const dispatch = useAppDispatch()
    const isSage = useIsSageTheme()

    const apiBaseUrl = useMemo(
        () => import.meta.env.VITE_API_URL || 'http://localhost:8000',
        []
    )

    // System browser opened this page with desktop_state → fetch Google OAuth URL and redirect
    const desktopState = searchParams.get('desktop_state')
    useEffect(() => {
        if (!desktopState || searchParams.get('desktop_auth')) return
        authService
            .getDesktopGoogleLoginUrl(desktopState)
            .then((url) => {
                window.location.href = url
            })
            .catch((err) => {
                console.error('Failed to get Google login URL:', err)
            })
    }, [desktopState, searchParams])

    if (desktopState && !searchParams.get('desktop_auth')) {
        return null
    }

    // Backend redirected back here after Google login completes
    if (searchParams.get('desktop_auth') === 'success') {
        return (
            <div className="flex flex-col items-center justify-center w-full h-full gap-4">
                <h2 className="text-2xl font-semibold text-firefly dark:text-sky-blue">
                    {t('auth.loginSuccessful', {
                        defaultValue: 'Login successful!'
                    })}
                </h2>
                <p className="text-firefly/70 dark:text-sky-blue/70">
                    {t('auth.closeTabMessage', {
                        defaultValue:
                            'You can close this tab and return to the app.'
                    })}
                </p>
            </div>
        )
    }

    const FormSchema = useMemo(
        () =>
            z.object({
                email: z.email({
                    error: t('auth.validation.invalidEmail')
                }),
                password: z
                    .string({
                        error: t('auth.validation.passwordRequired')
                    })
                    .min(6, {
                        message: t('auth.validation.passwordMinLength')
                    })
            }),
        [t]
    )

    const form = useForm<z.infer<typeof FormSchema>>({
        resolver: zodResolver(FormSchema),
        defaultValues: {
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
            } catch (error: unknown) {
                const apiError = error as {
                    response: { data: { detail: string } }
                }
                const errorMessage =
                    typeof apiError?.response?.data?.detail === 'string'
                        ? apiError.response.data.detail
                        : t('auth.loginFailed')
                if (errorMessage?.includes('beta')) {
                    toast.info(errorMessage)
                } else {
                    toast.error(errorMessage)
                }
            }
        },
        onError: (errorResponse) => {
            console.log('Login Failed:', errorResponse)
        }
    })

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
                storeAccessToken(payload.access_token)

                const userRes = await authService.getCurrentUser()
                dispatch(setUser(userRes))
                dispatch(fetchWishlist())
                dispatch(fetchPins())

                // Focus desktop app window after login
                if (isTauri) {
                    const { getCurrentWindow } = await import(
                        '@tauri-apps/api/window'
                    )
                    await getCurrentWindow().setFocus()
                }

                navigate('/')
            } catch (error) {
                console.error('Failed to finalize login:', error)
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

            if (
                !data ||
                (data.type !== 'ii-auth-success' &&
                    data.type !== 'google-auth-success')
            ) {
                return
            }

            void handleAuthSuccess(data.payload)
        }

        window.addEventListener('message', handler)
        return () => window.removeEventListener('message', handler)
    }, [apiOrigin, handleAuthSuccess])

    useEffect(() => {
        const hash = window.location.hash
        if (!hash) return

        // Support both II and Google auth hash-fragment fallbacks
        const authKey = hash.includes('ii-auth=')
            ? 'ii-auth'
            : hash.includes('google-auth=')
              ? 'google-auth'
              : null
        if (!authKey) return

        const params = new URLSearchParams(hash.slice(1))
        const encoded = params.get(authKey)
        params.delete(authKey)

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
            console.error('Failed to parse auth payload from hash:', error)
            authHandledRef.current = false
        }
    }, [handleAuthSuccess])

    const loginWithGoogleDesktop = useCallback(async () => {
        authHandledRef.current = false

        const state = crypto.randomUUID()
        const frontendOrigin =
            import.meta.env.VITE_FRONTEND_URL || 'http://localhost:1420'
        const url = `${frontendOrigin}/login?desktop_state=${state}`

        const { open } = await import('@tauri-apps/plugin-shell')
        await open(url)

        // Poll for token until backend stores it after Google callback
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
        console.log(data)
    }

    const hideSigninWithPassword = true

    return (
        <div className="flex flex-col items-center justify-center w-full h-full">
            <h1 className="text-[25px] md:text-[32px] font-semibold text-firefly dark:text-sky-blue">
                {t('auth.welcomeTitle', {
                    appName: isSage ? 'SAGE' : t('common.appName')
                })}
            </h1>
            <p className="text-[20px] md:text-[28px] text-firefly dark:text-sky-blue mb-12">
                {t('auth.welcomeSubtitle')}
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
                                                        placeholder={t(
                                                            'auth.emailPlaceholder'
                                                        )}
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
                                                            placeholder={t(
                                                                'auth.passwordPlaceholder'
                                                            )}
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
                                        {t('auth.forgotPassword')}
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
                                    {t('auth.signIn')}
                                </Button>
                            </div>
                        </form>
                    </Form>
                    <div className="flex justify-center items-center gap-2 text-black dark:text-white text-sm mt-8">
                        <span>{t('auth.noAccount')}</span>
                        <Link
                            to="/signup"
                            className="text-black dark:text-white text-sm font-semibold"
                        >
                            {t('auth.signUp')}
                        </Link>
                    </div>
                    <div className="flex w-full items-center gap-4 my-10">
                        <p className="flex-1 bg-black/[0.31] dark:bg-white/[0.31] h-[1px]"></p>
                        <span className="text-sm text-black dark:text-white font-semibold">
                            {t('common.or')}
                        </span>
                        <p className="flex-1 bg-black/[0.31] dark:bg-white/[0.31] h-[1px]"></p>
                    </div>
                </div>
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
                    {t('auth.continueWithII')}
                </Button>
                <p className="text-xs text-center text-firefly/70 dark:text-sky-blue/70 mt-6">
                    {t('auth.privacyNotice')} <br></br>
                    <a
                        href="/privacy"
                        className="underline hover:text-firefly dark:hover:text-sky-blue"
                    >
                        {t('auth.privacyNoticeLink')}
                    </a>
                </p>
            </div>
        </div>
    )
}

export const Component = LoginPage
