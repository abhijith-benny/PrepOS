import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy API requests to FastAPI backend while letting Vite handle SPA client routes
const apiProxy = {
  target: 'http://127.0.0.1:8000',
  changeOrigin: true,
  bypass: (req) => {
    // If request is from browser navigating to a page (Accept: text/html), serve the React SPA index.html
    if (req.headers.accept && req.headers.accept.includes('text/html')) {
      return '/index.html'
    }
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': apiProxy,
      '/me': apiProxy,
      '/topics': apiProxy,
      '/skills': apiProxy,
      '/attempts': apiProxy,
      '/diagnostic': apiProxy,
      '/schedule': apiProxy,
      '/srs': apiProxy,
      '/interview': apiProxy,
      '/coding': apiProxy,
    },
  },
})
