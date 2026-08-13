import { describe, expect, it } from 'vitest'

import { resolveApiBaseUrl, resolveApiOrigin } from '../api-base-url'

describe('resolveApiBaseUrl', () => {
    it('prefers explicitly configured base URL', () => {
        const resolved = resolveApiBaseUrl({
            configuredBaseUrl: 'https://api.example.com '
        })
        expect(resolved).toBe('https://api.example.com')
    })

    it('infers host:8000 for non-loopback browser hosts', () => {
        const resolved = resolveApiBaseUrl({
            configuredBaseUrl: '',
            location: {
                protocol: 'https:',
                hostname: 'app.example.com'
            }
        })
        expect(resolved).toBe('https://app.example.com:8000')
    })

    it('falls back to localhost when host is loopback', () => {
        const resolved = resolveApiBaseUrl({
            configuredBaseUrl: '',
            location: {
                protocol: 'http:',
                hostname: 'localhost'
            }
        })
        expect(resolved).toBe('http://localhost:8000')
    })
})

describe('resolveApiOrigin', () => {
    it('returns URL origin for valid absolute URL', () => {
        expect(resolveApiOrigin('https://api.example.com:8000/path')).toBe(
            'https://api.example.com:8000'
        )
    })

    it('returns raw value when URL parsing fails', () => {
        expect(resolveApiOrigin('not a url')).toBe('not a url')
    })
})