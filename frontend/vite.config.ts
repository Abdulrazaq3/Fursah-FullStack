import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'FURSAH_');
  const target = env.FURSAH_DEV_API_TARGET || 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1', port: 5173, strictPort: true,
      proxy: Object.fromEntries(['/api', '/health', '/ready'].map(path => [path, { target, changeOrigin: true }])),
    },
  };
});
