import { createBrowserRouter, RouterProvider } from 'react-router'
import { ProtectedRoute } from '@/components/protected-route'
import { RootLayout } from '@/components/layouts/root-layout'

const createAppRouter = () =>
    createBrowserRouter([
        {
            path: '/',
            element: <RootLayout />,
            children: [
                {
                    index: true,
                    async lazy() {
                        const { Component } = await import('@/app/routes/home')
                        return {
                            Component: () => <Component />
                        }
                    }
                },
                {
                    path: 'login',
                    async lazy() {
                        const { AuthLayout } = await import(
                            '@/components/layouts/auth-layout'
                        )
                        return { Component: AuthLayout }
                    },
                    children: [
                        {
                            index: true,
                            lazy: () => import('@/app/routes/login')
                        }
                    ]
                },
                {
                    path: 'signup',
                    async lazy() {
                        const { AuthLayout } = await import(
                            '@/components/layouts/auth-layout'
                        )
                        return { Component: AuthLayout }
                    },
                    children: [
                        {
                            index: true,
                            lazy: () => import('@/app/routes/signup')
                        }
                    ]
                },
                {
                    path: 'forgot-password',
                    async lazy() {
                        const { AuthLayout } = await import(
                            '@/components/layouts/auth-layout'
                        )
                        return { Component: AuthLayout }
                    },
                    children: [
                        {
                            index: true,
                            lazy: () => import('@/app/routes/forgot-password')
                        }
                    ]
                },
                {
                    path: 'terms',
                    async lazy() {
                        const { PublicLayout } = await import(
                            '@/components/layouts/public-layout'
                        )
                        return { Component: PublicLayout }
                    },
                    children: [
                        {
                            index: true,
                            lazy: () => import('@/app/routes/terms-of-use')
                        }
                    ]
                },
                {
                    path: 'privacy',
                    async lazy() {
                        const { PublicLayout } = await import(
                            '@/components/layouts/public-layout'
                        )
                        return { Component: PublicLayout }
                    },
                    children: [
                        {
                            index: true,
                            lazy: () => import('@/app/routes/privacy-policy')
                        }
                    ]
                },
                {
                    path: 'dashboard',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/dashboard'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'settings',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/settings'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'settings/:tab',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/settings'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'settings/usage/:sessionId',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/session-usage'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'settings/ledger/:sessionId',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/session-ledger'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'settings/reservations/:sessionId',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/session-reservations'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'chat',
                    async lazy() {
                        const { Component } = await import('@/app/routes/chat')
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'billing/success',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/billing-success'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'billing/cancel',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/billing-cancel'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'ii-claw',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/ii-claw'
                        )
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: 'share/:sessionId',
                    async lazy() {
                        const { Component } = await import('@/app/routes/share')
                        return { Component }
                    }
                },
                {
                    path: 'presentations/:sessionId',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/presentations'
                        )
                        return { Component }
                    }
                },
                {
                    path: 'storybooks/:storybookId',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/storybooks'
                        )
                        return { Component }
                    }
                },
                {
                    path: 'auth/oauth/google/callback',
                    async lazy() {
                        const { GoogleDriveCallback } = await import(
                            '@/app/routes/google-drive-callback'
                        )
                        return { Component: GoogleDriveCallback }
                    }
                },
                {
                    path: 'auth/oauth/github/callback',
                    async lazy() {
                        const { GitHubCallback } = await import(
                            '@/app/routes/github-callback'
                        )
                        return { Component: GitHubCallback }
                    }
                },
                {
                    path: 'auth/oauth/revenuecat/callback',
                    async lazy() {
                        const { RevenueCatCallback } = await import(
                            '@/app/routes/revenuecat-callback'
                        )
                        return { Component: RevenueCatCallback }
                    }
                },
                {
                    path: 'google-drive-callback',
                    async lazy() {
                        const { GoogleDriveCallback } = await import(
                            '@/app/routes/google-drive-callback'
                        )
                        return { Component: GoogleDriveCallback }
                    }
                },
                {
                    path: 'auth/oauth/composio/callback',
                    async lazy() {
                        const { ComposioOAuthCallback } = await import(
                            '@/app/routes/composio-oauth-callback'
                        )
                        return { Component: ComposioOAuthCallback }
                    }
                },
                {
                    path: 'oauth/consent',
                    async lazy() {
                        const { Component } = await import(
                            '@/app/routes/oauth-consent'
                        )
                        return {
                            Component: () => <Component />
                        }
                    }
                },
                {
                    path: ':sessionId',
                    async lazy() {
                        const { Component } = await import('@/app/routes/agent')
                        return {
                            Component: () => (
                                <ProtectedRoute>
                                    <Component />
                                </ProtectedRoute>
                            )
                        }
                    }
                },
                {
                    path: '*',
                    lazy: () => import('@/app/routes/not-found')
                }
            ]
        }
    ])

export default function AppRouter() {
    return <RouterProvider router={createAppRouter()} />
}
