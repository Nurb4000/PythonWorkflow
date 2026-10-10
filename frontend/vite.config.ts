import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// E9: Bundle analysis — enabled when VITE_ANALYZE=1 or --mode analyze
const isAnalyze = process.env.VITE_ANALYZE === '1' || process.env.NODE_ENV === 'analyze'

export default defineConfig({
  plugins: [
    react(),
    ...(isAnalyze
      ? [
          (async () => {
            const { bundleAnalyzerPlugin } = await import('rollup-plugin-visualizer')
            return bundleAnalyzerPlugin({
              open: true,
              filename: 'dist/stats.html',
              gzipSize: true,
              brotliSize: true,
            })
          })(),
        ]
      : []),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    // Suggest code splitting for large libraries
    rollupOptions: {
      output: {
        manualChunks: {
          // Split React Flow into its own chunk (large dependency)
          reactflow: ['@xyflow/react', 'reactflow'],
          // Split React Router into its own chunk
          reactRouter: ['react-router-dom'],
          // Split TanStack Query into its own chunk
          reactQuery: ['@tanstack/react-query'],
        }
      }
    }
  }
})
