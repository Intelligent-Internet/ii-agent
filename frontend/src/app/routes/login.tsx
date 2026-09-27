import { useGoogleLogin } from '@react-oauth/google'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { ACCESS_TOKEN } from '@/constants/auth'
import { authService } from '@/services/auth.service'
import { useAppDispatch } from '@/state/store'
import { setUser } from '@/state/slice/user'
import { fetchWishlist } from '@/state/slice/favorites'
import { fetchPins } from '@/state/slice/pins'
import { toast } from 'sonner'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

type IiAuthPayload = {
    access_token: string
    refresh_token?: string
    token_type?: string
    expires_in?: number
}

export function LoginPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const { loginWithAuthCode } = useAuth()
    const dispatch = useAppDispatch()
    const isSage = useIsSageTheme()

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
                dispatch(fetchPins())

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
                    onClick={() => googleLogin()}
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
                <DevLoginButton
                    apiBaseUrl={apiBaseUrl}
                    onSuccess={handleAuthSuccess}
                />
                <p className="text-xs text-center text-firefly/70 dark:text-sky-blue/70 mt-6">
                    {t('auth.privacyNotice')}{' '}
                    <br></br>
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

/**
 * Dev login chooser - only shows when SANDBOX_LOCAL_MODE=true and DEV_USERS
 * is configured on the backend. Each named dev user maps to a distinct
 * database user (email dev+<username>@localhost), giving full session/credit
 * isolation between household members.
 */
type DevUserPublic = { username: string; display_name: string }
type DevUsersResponse = { enabled: boolean; users: DevUserPublic[] }

function DevLoginButton({
    apiBaseUrl,
    onSuccess
}: {
    apiBaseUrl: string
    onSuccess: (payload: IiAuthPayload | null | undefined) => Promise<void>
}) {
    const [users, setUsers] = useState<DevUserPublic[] | null>(null)
    const [selected, setSelected] = useState<string>('')
    const [pin, setPin] = useState<string>('')
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        fetch(`${apiBaseUrl}/auth/dev/users`)
            .then(async (res) => {
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`)
                }
                return (await res.json()) as DevUsersResponse
            })
            .then((data) => {
                if (cancelled) return
                if (data.enabled && data.users.length > 0) {
                    setUsers(data.users)
                    setSelected(data.users[0].username)
                } else {
                    setUsers([])
                }
            })
            .catch(() => {
                if (!cancelled) setUsers([])
            })
        return () => {
            cancelled = true
        }
    }, [apiBaseUrl])

    const handleDevLogin = async () => {
        setError(null)
        if (!selected || pin.length < 4) {
            setError('Pick a user and enter the PIN')
            return
        }
        setSubmitting(true)
        try {
            const res = await fetch(`${apiBaseUrl}/auth/dev/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: selected, pin })
            })
            if (!res.ok) {
                let msg = 'Dev login failed'
                try {
                    const body = await res.json()
                    if (typeof body?.detail === 'string') msg = body.detail
                } catch {
                    /* ignore body parse errors */
                }
                throw new Error(msg)
            }
            const data = await res.json()
            setPin('')
            await onSuccess(data)
        } catch (err) {
            console.error('Dev login failed:', err)
            setError(err instanceof Error ? err.message : 'Dev login failed')
        } finally {
            setSubmitting(false)
        }
    }

    if (users === null) {
        // Probe still in flight — render nothing to avoid flicker.
        return null
    }
    if (users.length === 0) {
        return null
    }

    return (
        <div className="w-full mt-4 flex flex-col gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
            <div className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                Local-mode dev login
            </div>
            <div className="flex gap-2">
                <select
                    value={selected}
                    onChange={(e) => setSelected(e.target.value)}
                    disabled={submitting}
                    className="flex-1 rounded-md border border-input bg-background text-foreground px-3 py-2 text-sm"
                >
                    {users.map((u) => (
                        <option
                            key={u.username}
                            value={u.username}
                            className="bg-background text-foreground"
                        >
                            {u.display_name}
                        </option>
                    ))}
                </select>
                <Input
                    type="password"
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="PIN"
                    value={pin}
                    disabled={submitting}
                    onChange={(e) => setPin(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') void handleDevLogin()
                    }}
                    className="w-28"
                />
            </div>
            {error && (
                <div className="text-xs text-red-600 dark:text-red-400">
                    {error}
                </div>
            )}
            <Button
                size="lg"
                onClick={handleDevLogin}
                disabled={submitting || !selected || pin.length < 4}
                className="w-full bg-amber-500 hover:bg-amber-600 text-black font-semibold shadow-btn"
            >
                {submitting ? 'Signing in…' : `Sign in as ${selected || '…'}`}
            </Button>
        </div>
    )
}

export const Component = LoginPage
