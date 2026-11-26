/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Endereço da API (src/api/config.ts). Público: vai para o navegador. */
  readonly VITE_CONTAAI_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
