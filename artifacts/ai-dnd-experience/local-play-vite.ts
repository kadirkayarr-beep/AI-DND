import type { Plugin } from 'vite';

// The UI half of api/local_play.py. A forged flag reaches nothing: the server still decides.
export const LOCAL_PLAY_ALLOWED_HOSTS = ['localhost', '127.0.0.1'];

const CLERK_ENTRY = 'src="/src/main.tsx"';
const LOCAL_ENTRY = 'src="/src/local-play-main.tsx"';
const HOSTED_KEYS = [
  'REPL_ID',
  'REPLIT_DEPLOYMENT',
  'REPLIT_DEV_DOMAIN',
  'REPLIT_DOMAINS',
  'REPLIT_APP_DOMAIN',
];

export function localPlayRequested(env: NodeJS.ProcessEnv): boolean {
  if (env.VITE_AI_DND_LOCAL_PLAY !== '1') return false;
  const hosted = HOSTED_KEYS.some((key) => env[key] !== undefined);
  if (hosted || env.NODE_ENV === 'production') {
    throw new Error('Local play refuses a hosted or production environment.');
  }
  return true;
}

export function localPlayPlugin(): Plugin {
  return {
    name: 'ai-dnd-local-play',
    config(_config, env) {
      if (env.command !== 'serve' || env.isPreview) {
        throw new Error('Local play exists only on the dev server, never in a build or preview.');
      }
    },
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        return html.replace(CLERK_ENTRY, LOCAL_ENTRY);
      },
    },
  };
}
