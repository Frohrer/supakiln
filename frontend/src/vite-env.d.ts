/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_CF_CLIENT_ID: string
  readonly VITE_CF_CLIENT_SECRET: string
  readonly VITE_CF_ACCESS_TOKEN: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
} 