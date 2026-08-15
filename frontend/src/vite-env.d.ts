/// <reference types="vite/client" />
/// <reference types="vite/client" />
/// <reference types="vite-plugin-svgr/client" />

interface ImportMetaEnv {
    readonly VITE_API_URL: string
    readonly VITE_GOOGLE_CLIENT_ID?: string
    readonly VITE_STRIPE_PUBLISHABLE_KEY?: string
    readonly VITE_FRONTEND_URL?: string
}

interface ImportMeta {
    readonly env: ImportMetaEnv
}
