/// <reference types="vitest/config" />
import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, searchForWorkspaceRoot, type Plugin } from 'vite';
import { cabecalhosDeSeguranca, politicaDeSeguranca } from './csp.ts';

// A tela roda em http://127.0.0.1:3000, uma origem da lista do backend (Origin nos POST, ADR 0011).
// strictPort: se a porta estiver ocupada, falha em vez de subir em outra porta, que o backend recusaria.
const PORTA = { host: '127.0.0.1', port: 3000, strictPort: true } as const;

// Endereço da API para o proxy /api (ADR 0015). Fica no servidor do Vite e não vai para o navegador (não é
// VITE_*). O proxy tira o /api do caminho: /api/catalogo chega à API como /catalogo.
const API_LOCAL = 'http://127.0.0.1:8000';

function proxyDaApi(alvo: string) {
  return {
    '/api': {
      target: alvo,
      rewrite: (caminho: string) => caminho.replace(/^\/api/, ''),
    },
  };
}

// As notas de exemplo (C2c, ADR 0016): os XML fictícios de data/demo/notas, os mesmos das sementes e dos testes
// do backend. A tela os importa de lá (src/dados/notasDeExemplo.ts), sem cópia. O servidor de desenvolvimento só
// serve arquivos de dentro de server.fs.allow, e definir essa lista troca a raiz padrão por ela (Vite 8.3.8,
// resolveServerOptions: `raw?.fs?.allow ?? [workspaceRoot]`). Por isso a lista repete a raiz padrão
// (searchForWorkspaceRoot) e soma só essa pasta, que tem apenas XML fictícios. A lista de deny padrão (.env,
// chaves, .git) continua valendo. O build e o preview não usam essa lista.
const PASTA_DAS_NOTAS = resolve(import.meta.dirname, '../data/demo/notas');

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
  const alvo = loadEnv(mode, import.meta.dirname, 'CONTAAI_').CONTAAI_API_ALVO || API_LOCAL;
  return {
    plugins: [react(), cspNoBuild(api)],
    server: {
      ...PORTA,
      proxy: proxyDaApi(alvo),
      fs: { allow: [searchForWorkspaceRoot(import.meta.dirname), PASTA_DAS_NOTAS] },
    },
    // O preview serve o build com os cabeçalhos e o proxy /api que a E6 vai repetir.
    preview: { ...PORTA, headers: cabecalhosDeSeguranca(api), proxy: proxyDaApi(alvo) },
    build: {
      // Sem mapas de código no build publicado.
      sourcemap: false,
      // O XML sai sempre como arquivo: abaixo de 4 KB (o padrão), o Vite o embutiria no código como data:, e a
      // nota 1 (2.394 bytes) e a nota sem par (1.769) virariam texto em base64 no lugar de um arquivo para baixar.
      assetsInlineLimit: (arquivo) => (arquivo.endsWith('.xml') ? false : undefined),
      // As licenças das bibliotecas que vão no navegador, num arquivo ao lado do build: a MIT pede que o aviso
      // de copyright acompanhe as cópias, e o código minificado sai sem os comentários de licença. O Vite
      // monta a lista só com o que entra no build (build.license, Vite 8).
      license: { fileName: 'licencas.md' },
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
