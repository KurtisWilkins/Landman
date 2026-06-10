/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_API_TARGET?: string;
  readonly VITE_RELEASE?: string;
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_SENTRY_ENVIRONMENT?: string;
  readonly VITE_DEV_BEARER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
