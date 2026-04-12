import { describe, expect, it } from 'vitest'
import { isSandboxLink, isE2bLink, rewriteLocalhostUrl } from '../utils'

describe('isSandboxLink', () => {
    describe('E2B cloud sandbox URLs', () => {
        it('matches typical E2B sandbox URL', () => {
            expect(isSandboxLink('https://abc123.e2b.dev/')).toBe(true)
        })

        it('matches E2B URL with port', () => {
            expect(isSandboxLink('https://abc123.e2b.dev:3000/path')).toBe(true)
        })

        it('matches hostname containing e2b anywhere', () => {
            expect(isSandboxLink('https://sandbox-e2b-something.example.com/')).toBe(true)
        })
    })

    describe('local Docker sandbox URLs', () => {
        it('matches localhost with port', () => {
            expect(isSandboxLink('http://localhost:8080/')).toBe(true)
        })

        it('matches 127.0.0.1 with port', () => {
            expect(isSandboxLink('http://127.0.0.1:3000/')).toBe(true)
        })

        it('matches 192.168.x.x with port', () => {
            expect(isSandboxLink('http://192.168.2.2:8080/')).toBe(true)
            expect(isSandboxLink('http://192.168.1.100:3000/')).toBe(true)
        })

        it('matches 10.x.x.x with port', () => {
            expect(isSandboxLink('http://10.0.0.1:8080/')).toBe(true)
            expect(isSandboxLink('http://10.255.255.255:3000/')).toBe(true)
        })

        it('matches 172.16-31.x.x with port', () => {
            expect(isSandboxLink('http://172.16.0.1:8080/')).toBe(true)
            expect(isSandboxLink('http://172.31.255.255:3000/')).toBe(true)
        })

        it('rejects localhost without port', () => {
            expect(isSandboxLink('http://localhost/')).toBe(false)
        })

        it('rejects 127.0.0.1 without port', () => {
            expect(isSandboxLink('http://127.0.0.1/')).toBe(false)
        })

        it('rejects private IP without port', () => {
            expect(isSandboxLink('http://192.168.1.1/')).toBe(false)
        })
    })

    describe('non-sandbox URLs', () => {
        it('rejects public domain', () => {
            expect(isSandboxLink('https://example.com/')).toBe(false)
        })

        it('rejects public domain with port', () => {
            expect(isSandboxLink('https://example.com:8080/')).toBe(false)
        })

        it('rejects S3/presigned URLs', () => {
            expect(isSandboxLink('https://s3.amazonaws.com/bucket/file.png')).toBe(false)
        })

        it('rejects 172.32+ (not private range)', () => {
            expect(isSandboxLink('http://172.32.0.1:8080/')).toBe(false)
        })

        it('rejects 172.15 (not private range)', () => {
            expect(isSandboxLink('http://172.15.0.1:8080/')).toBe(false)
        })
    })

    describe('edge cases', () => {
        it('returns false for empty string', () => {
            expect(isSandboxLink('')).toBe(false)
        })

        it('returns false for invalid URL', () => {
            expect(isSandboxLink('not-a-url')).toBe(false)
        })

        it('returns false for plain text', () => {
            expect(isSandboxLink('hello world')).toBe(false)
        })
    })
})

describe('isE2bLink', () => {
    it('matches E2B URLs', () => {
        expect(isE2bLink('https://abc123.e2b.dev/')).toBe(true)
        expect(isE2bLink('https://sandbox-e2b-foo.example.com/')).toBe(true)
    })

    it('rejects localhost URLs (narrow check for free text)', () => {
        expect(isE2bLink('http://localhost:8080/')).toBe(false)
        expect(isE2bLink('http://192.168.2.2:3000/')).toBe(false)
    })

    it('rejects public domains', () => {
        expect(isE2bLink('https://example.com/')).toBe(false)
    })

    it('returns false for invalid input', () => {
        expect(isE2bLink('')).toBe(false)
        expect(isE2bLink('not-a-url')).toBe(false)
    })
})

describe('rewriteLocalhostUrl', () => {
    it('rewrites localhost URL to browser host for guest/LAN access', () => {
        expect(rewriteLocalhostUrl('http://localhost:30003/', '192.168.2.2')).toBe(
            'http://192.168.2.2:30003/'
        )
    })

    it('rewrites private-ip URL to localhost for host-local access', () => {
        expect(rewriteLocalhostUrl('http://192.168.2.2:30003/', 'localhost')).toBe(
            'http://localhost:30003/'
        )
    })

    it('keeps non-local public URLs unchanged', () => {
        expect(rewriteLocalhostUrl('https://example.com/path', 'localhost')).toBe(
            'https://example.com/path'
        )
    })
})
