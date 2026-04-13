import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

export const parseJson = (jsonString: string) => {
    try {
        return JSON.parse(jsonString)
    } catch {
        return null
    }
}

export const getFirstCharacters = (str: string) => {
    return str
        .trim()
        .split(/\s+/)
        .map((word) => word.charAt(0).toUpperCase())
        .join('')
}

/**
 * Rewrite localhost URLs to use the current browser hostname when accessed
 * from a non-localhost host (e.g. LAN IP). This ensures sandbox port URLs
 * are reachable from the user's machine.
 */
export const rewriteLocalhostUrl = (
    url: string,
    browserHost: string = window.location.hostname
): string => {
    try {
        const parsed = new URL(url)
        const targetHost = parsed.hostname
        const isBrowserLocal = browserHost === 'localhost' || browserHost === '127.0.0.1'
        const isTargetLocal = targetHost === 'localhost' || targetHost === '127.0.0.1'
        const isPrivateIp = /^(10|172\.(1[6-9]|2\d|3[01])|192\.168)\./.test(targetHost)

        // Guest/LAN access: localhost links from backend must point to current host.
        if (!isBrowserLocal && isTargetLocal) {
            parsed.hostname = browserHost
            return parsed.toString()
        }

        // Host-local access: if backend emits LAN IP but app is accessed locally,
        // normalize to localhost for environments using local port forwarding.
        if (isBrowserLocal && isPrivateIp) {
            parsed.hostname = browserHost
            return parsed.toString()
        }

        return url
    } catch {
        return url
    }
}

export const extractUrls = (markdown: string) => {
    const urlRegex = /\[.*?\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s)]+)/g

    const urls: string[] = []
    let match: RegExpExecArray | null

    while ((match = urlRegex.exec(markdown)) !== null) {
        let url = match[1] || match[2]
        if (url) {
            // Remove trailing markdown punctuation like **, _, ., ,, ), etc.
            url = url
                .replace(/[*_]+$/g, '')
                .replace(/[.,)]+$/g, '')
                .replace(/[*_.,!?`)+]+$/g, '')
            urls.push(rewriteLocalhostUrl(url))
        }
    }

    return urls
}

export const isImageFile = (fileName: string): boolean => {
    const ext = fileName.split('.').pop()?.toLowerCase() || ''
    return [
        'jpg',
        'jpeg',
        'png',
        'gif',
        'webp',
        'bmp',
        'heic',
        'heif',
        'svg',
        'avif',
        'apng',
        'tif',
        'tiff',
        'ico'
    ].includes(ext)
}

export const formatDuration = (milliseconds: number): string => {
    if (milliseconds < 1000) {
        return `${milliseconds}ms`
    }

    const seconds = Math.floor(milliseconds / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)

    if (hours > 0) {
        const remainingMinutes = minutes % 60
        return `${hours}h ${remainingMinutes}m`
    }

    if (minutes > 0) {
        const remainingSeconds = seconds % 60
        return `${minutes}m ${remainingSeconds}s`
    }

    return `${seconds}s`
}

/**
 * Check if a URL points to a sandbox (E2B cloud or local Docker).
 *
 * E2B:   https://<id>.e2b.dev/...
 * Local: http://localhost:<port>/... or http://<private-ip>:<port>/...
 */
export const isSandboxLink = (url: string): boolean => {
    try {
        const parsed = new URL(url)
        const host = parsed.hostname

        // E2B cloud sandbox
        if (host.includes('e2b')) return true

        // Local Docker sandbox (localhost or private IP with a mapped port)
        if (
            (host === 'localhost' || host === '127.0.0.1' || /^(10|172\.(1[6-9]|2\d|3[01])|192\.168)\./.test(host)) &&
            parsed.port !== ''
        ) {
            return true
        }

        return false
    } catch {
        return false
    }
}

/**
 * E2B-specific URL check. Use for matching URLs extracted from free text
 * where localhost URLs could be false positives.
 */
export const isE2bLink = (url: string): boolean => {
    try {
        return new URL(url).hostname.includes('e2b')
    } catch {
        return false
    }
}

export const identifyFilesNeeded = (text: string): string[] => {
    const lines = text.split(/\r?\n/)
    const updates = lines
        .filter((line) => line.startsWith('*** Update File: '))
        .map((line) => line.substring('*** Update File: '.length))

    const deletes = lines
        .filter((line) => line.startsWith('*** Delete File: '))
        .map((line) => line.substring('*** Delete File: '.length))

    const adds = lines
        .filter((line) => line.startsWith('*** Add File: '))
        .map((line) => line.substring('*** Add File: '.length))
    return [...adds, ...updates, ...deletes]
}

export const identifySlidesNeeded = (text: string): string[] => {
    const lines = text.split(/\r?\n/)
    const updates = lines
        .filter((line) => line.startsWith('*** Update Slide: '))
        .map((line) => line.substring('*** Update Slide: '.length))

    const adds = lines
        .filter((line) => line.startsWith('*** Add Slide: '))
        .map((line) => line.substring('*** Add Slide: '.length))

    return [...adds, ...updates]
}

export const isValidBase64 = (str: string) => {
    if (!str || str.trim() === '') return false

    // Base64 strings should have length multiple of 4
    if (str.length % 4 !== 0) return false

    // Regex to match only valid Base64 characters
    const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/
    return base64Regex.test(str)
}
