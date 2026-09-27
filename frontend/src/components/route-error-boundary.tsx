import { isRouteErrorResponse, useNavigate, useRouteError } from 'react-router'

// Catches render-time errors thrown anywhere under the route's element tree.
// Without this, react-router renders its built-in "Hey developer 👋" panel
// and the stack from a minified build is opaque (e.g. React error #185 with
// no component name). This panel shows the error message + stack so prod
// crashes are at least copy-pasteable, and offers a Reload escape hatch.
export function RouteErrorBoundary() {
    const error = useRouteError()
    const navigate = useNavigate()

    let title = 'Something went wrong'
    let message = 'An unexpected error occurred while rendering this page.'
    let stack: string | undefined

    if (isRouteErrorResponse(error)) {
        title = `${error.status} ${error.statusText}`
        message = typeof error.data === 'string' ? error.data : message
    } else if (error instanceof Error) {
        message = error.message || message
        stack = error.stack
    } else if (typeof error === 'string') {
        message = error
    }

    if (typeof console !== 'undefined') {
        // Surface the raw error so devs can grab the un-flattened object.
        console.error('[RouteErrorBoundary]', error)
    }

    return (
        <div className="flex min-h-screen items-center justify-center p-6">
            <div className="max-w-2xl w-full rounded-xl border border-red-300/40 bg-white/80 dark:bg-black/40 backdrop-blur-sm p-6 shadow-lg">
                <h1 className="text-2xl font-semibold text-black dark:text-white mb-2">
                    {title}
                </h1>
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-4 whitespace-pre-wrap break-words">
                    {message}
                </p>
                {stack && (
                    <details className="mb-4">
                        <summary className="cursor-pointer text-xs text-gray-500 dark:text-gray-400">
                            Stack trace
                        </summary>
                        <pre className="mt-2 max-h-64 overflow-auto rounded bg-black/5 dark:bg-white/5 p-3 text-[11px] leading-snug text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-words">
                            {stack}
                        </pre>
                    </details>
                )}
                <div className="flex gap-2">
                    <button
                        type="button"
                        onClick={() => window.location.reload()}
                        className="px-4 py-2 rounded-lg bg-firefly dark:bg-sky-blue text-sky-blue dark:text-black text-sm font-medium hover:opacity-80 transition-opacity"
                    >
                        Reload
                    </button>
                    <button
                        type="button"
                        onClick={() => navigate('/', { replace: true })}
                        className="px-4 py-2 rounded-lg border border-gray-400 dark:border-gray-600 text-sm font-medium text-black dark:text-white hover:opacity-80 transition-opacity"
                    >
                        Go home
                    </button>
                </div>
            </div>
        </div>
    )
}
