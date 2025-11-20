import path from 'path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import svgr from 'vite-plugin-svgr'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react(), tailwindcss(), svgr()],

    // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
    //
    // 1. prevent vite from obscuring rust errors
    clearScreen: false,
    // 2. tauri expects a fixed port, fail if that port is not available
    server: {
        port: 1420,
        strictPort: true,
        watch: {
            // 3. tell vite to ignore watching `src-tauri`
            ignored: ['**/src-tauri/**']
        },
        proxy: {
            '/auth': {
                target: 'http://localhost:3000',
                changeOrigin: true,
            },
            '/api': {
                target: 'http://localhost:3000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, '')
            }
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
            // Disable tree shaking completely
            treeshake: false
        },

        // Disable certain optimizations that can cause the error
        minify: false,

        target: 'esnext'
    }
})
