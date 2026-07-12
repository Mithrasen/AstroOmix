import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// No dev proxy on purpose.
//
// In production the frontend (Vercel) calls the backend (Render) directly at a
// different origin, relying on CORS. If dev went through a Vite proxy instead,
// dev and prod would exercise different network paths and CORS bugs would only
// ever surface after deploy. Dev uses the same direct, cross-origin call — see
// .env.development.
//
// Vite's dev proxy also truncated large JSON responses here: it stalled at a
// buffer boundary (255 KiB / 3060 KiB) on roughly half of requests to
// /api/abtest, delivering a partial body that never terminated.
export default defineConfig({
  plugins: [react()],
})
