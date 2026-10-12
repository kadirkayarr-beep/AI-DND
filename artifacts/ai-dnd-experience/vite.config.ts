import path from 'path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

import runtimeErrorOverlay from '@replit/vite-plugin-runtime-error-modal';

const rawPort = process.env.PORT;

if (!rawPort) {
  throw new Error(
    'PORT environment variable is required but was not provided.',
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

// Local development must not expose the unauthenticated campaign API to LAN.
// Replit needs a public listener, but only explicitly known hostnames are trusted.
const replitRuntime = process.env.REPL_ID !== undefined;
const listenHost = replitRuntime ? '0.0.0.0' : '127.0.0.1';
const allowedHosts = Array.from(new Set([
  'localhost',
  '127.0.0.1',
  process.env.REPLIT_DEV_DOMAIN,
  process.env.REPLIT_APP_DOMAIN,
  ...(process.env.REPLIT_DOMAINS || '').split(','),
  ...(process.env.AI_DND_ALLOWED_HOSTS || '').split(','),
].filter((value): value is string => Boolean(value?.trim())).map((value) => value.trim())));

const basePath = process.env.BASE_PATH;

if (!basePath) {
  throw new Error(
    'BASE_PATH environment variable is required but was not provided.',
  );
}

export default defineConfig({
  base: basePath,
  plugins: [
    react(),
    tailwindcss(),
    runtimeErrorOverlay(),
    ...(process.env.NODE_ENV !== 'production' &&
    process.env.REPL_ID !== undefined
      ? [
          await import('@replit/vite-plugin-cartographer').then((m) =>
            m.cartographer({
              root: path.resolve(import.meta.dirname, '..'),
            }),
          ),
          await import('@replit/vite-plugin-dev-banner').then((m) =>
            m.devBanner(),
          ),
        ]
      : []),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, 'src'),
      '@assets': path.resolve(
        import.meta.dirname,
        '..',
        '..',
        'attached_assets',
      ),
    },
    dedupe: ['react', 'react-dom'],
  },
  root: path.resolve(import.meta.dirname),
  build: {
    outDir: path.resolve(import.meta.dirname, 'dist/public'),
    emptyOutDir: true,
  },
  server: {
    port,
    strictPort: true,
    host: listenHost,
    allowedHosts,
    fs: {
      strict: true,
    },
    proxy: {
      '/api': {
        target: process.env.AI_DND_API_ORIGIN || 'http://127.0.0.1:8008',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port,
    host: listenHost,
    allowedHosts,
  },
});
