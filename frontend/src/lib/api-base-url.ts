type LocationLike = Pick<Location, 'protocol' | 'hostname'>

function isLoopbackHost(hostname: string): boolean {
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
}

export function resolveApiBaseUrl(options?: {
    configuredBaseUrl?: string | null
    location?: LocationLike | null
}): string {
    const configured = (options?.configuredBaseUrl ?? import.meta.env.VITE_API_URL ?? '').trim()
    if (configured) {
        return configured
    }

    const location =
        options?.location ?? (typeof window !== 'undefined' ? window.location : null)
    if (location && !isLoopbackHost(location.hostname)) {
        return `${location.protocol}//${location.hostname}:8000`
    }

    return 'http://localhost:8000'
}

export function resolveApiOrigin(baseUrl?: string): string {
    const resolved = baseUrl ?? resolveApiBaseUrl()
    try {
        return new URL(resolved).origin
    } catch {
        return resolved
    }
}