/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type Plugin } from 'vite';
import { cabecalhosDeSeguranca, politicaDeSeguranca } from './csp.ts';

// A tela roda em http://127.0.0.1:3000, a origem liberada no CORS do backend (ADR 0011).
// strictPort: se a porta estiver ocupada, falha em vez de subir em outra porta que o CORS recusaria.
const PORTA = { host: '127.0.0.1', port: 3000, strictPort: true } as const;

const CHARSET = '<meta charset="UTF-8" />';

/**
 * Põe a CSP como <meta> no index.html do build (docs/seguranca.md, regras da interface, item 3), logo depois
 * do charset: uma CSP em <meta> só vale para o que vem depois dela, então ela precisa vir antes de todo
 * script e estilo. Sem o charset no lugar esperado, o build falha em vez de sair sem a política.
 */
function cspNoBuild(api: string | undefined): Plugin {
  return {
    name: 'contaai-csp',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler: (html) => {
        if (html.split(CHARSET).length !== 2) {
          throw new Error(`index.html precisa ter exatamente um ${CHARSET} para receber a CSP`);
        }
        const politica = politicaDeSeguranca({ api, cabecalho: false }).replaceAll("'", '&#39;');
        return html.replace(CHARSET, `${CHARSET}\n    <meta http-equiv="Content-Security-Policy" content="${politica}" />`);
      },
    },
  };
}

export default defineConfig(({ mode }) => {
  // Só as variáveis VITE_*, que já são públicas (vão para o navegador).
  const api = loadEnv(mode, import.meta.dirname, 'VITE_').VITE_CONTAAI_API;
  return {
    plugins: [react(), cspNoBuild(api)],
    server: PORTA,
    // O preview serve o build com os cabeçalhos que a E6 vai repetir no proxy.
    preview: { ...PORTA, headers: cabecalhosDeSeguranca(api) },
    build: {
      // Sem mapas de código no build publicado.
      sourcemap: false,
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      // Por padrão o Vitest troca todo CSS por texto vazio, até no import ?raw. Os tokens são lidos pelo
      // teste de contraste (src/estilo/tokens.test.ts).
      css: { include: [/src\/estilo\/.+\.css/] },
    },
  };
});
