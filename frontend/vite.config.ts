import path from 'path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'
import svgr from 'vite-plugin-svgr'

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
    const env = loadEnv(mode, process.cwd(), '')
    const isSage = env.VITE_THEME?.toLowerCase() === 'sage'
    const disableBuildOptimizations =
        env.VITE_DISABLE_BUILD_OPTIMIZATIONS === 'true'
    const shouldOptimizeBuild = command === 'build' && !disableBuildOptimizations
    const sageHead = `<head>
        <meta charset="UTF-8" />
        <link
            rel="apple-touch-icon"
            sizes="180x180"
            href="/sage_favicon/apple-touch-icon.png"
        />
        <link
            rel="icon"
            type="image/png"
            sizes="32x32"
            href="/sage_favicon/favicon-32x32.png"
        />
        <link
            rel="icon"
            type="image/png"
            sizes="16x16"
            href="/sage_favicon/favicon-16x16.png"
        />
        <link rel="manifest" href="/sage_favicon/site.webmanifest" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>SAGE</title>

        <meta property="og:title" content="SAGE" />
        <meta property="og:url" content="/" />
        <meta property="og:site_name" content="SAGE" />
        <meta property="og:locale" content="en_US" />
        <meta
            property="og:image"
            content="https://webstatics.ii.inc/sage/sage-ogcard.png"
        />
        <meta property="og:type" content="website" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="SAGE" />
        <meta
            name="twitter:image"
            content="https://webstatics.ii.inc/sage/sage-ogcard.png"
        />
    </head>`
    const sageHeadPlugin = {
        name: 'sage-head',
        transformIndexHtml: {
            order: 'pre',
            handler(html) {
                if (!isSage) return html
                return html.replace(/<head>[\s\S]*?<\/head>/i, sageHead)
            }
        }
    }

    return {
        plugins: [sageHeadPlugin, react(), tailwindcss(), svgr()],

        // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
        //
        // 1. prevent vite from obscuring rust errors
        clearScreen: false,
        // 2. tauri expects a fixed port, fail if that port is not available
        server: {
            port: parseInt(env.VITE_PORT || '1420'),
            strictPort: true,
            watch: {
                // 3. tell vite to ignore watching `src-tauri`
                ignored: ['**/src-tauri/**']
            }
        },

        // Shadcn UI
        resolve: {
            alias: {
                '@': path.resolve(__dirname, './src')
            }
        },

        // Fix for "Cannot add property 0, object is not extensible" error
        build: {
            rollupOptions: {
                onwarn(warning, warn) {
                    // Suppress specific warnings that can cause the extensibility error
                    if (warning.code === 'CIRCULAR_DEPENDENCY') {
                        return
                    }
                    warn(warning)
                },
                output: {
                    // Disable tree-shaking optimizations that can cause the extensibility error
                    manualChunks: undefined
                },
                // Keep DCE enabled by default to avoid React production warnings.
                treeshake: shouldOptimizeBuild
            },

            // Allow opting out of build optimizations if the error resurfaces.
            minify: shouldOptimizeBuild ? 'esbuild' : false,

            // Hidden source maps: emit .map files for post-mortem debugging
            // without exposing them to the browser via sourceMappingURL.
            sourcemap: 'hidden',

            target: 'esnext'
        }
    }
})
