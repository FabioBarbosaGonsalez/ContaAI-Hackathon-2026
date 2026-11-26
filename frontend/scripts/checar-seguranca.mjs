#!/usr/bin/env node
// Checagem de segurança do código e do build da tela (docs/seguranca.md, regras da interface).
// Roda no CI depois do `vite build`: `npm run seguranca`. Sai com código 1 se achar qualquer problema.
//
// O lint (eslint.config.js) já barra esses padrões no código; esta é a segunda barreira, por busca no texto,
// e a única que olha o build publicado (dist/).

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';
import { loadEnv } from 'vite';
import { politicaDeSeguranca } from '../csp.ts';

const RAIZ = resolve(import.meta.dirname, '..');
const SRC = join(RAIZ, 'src');
const DIST = join(RAIZ, 'dist');
const problemas = [];

function arquivos(pasta) {
  return readdirSync(pasta).flatMap((nome) => {
    const caminho = join(pasta, nome);
    return statSync(caminho).isDirectory() ? arquivos(caminho) : [caminho];
  });
}

const rel = (caminho) => relative(RAIZ, caminho).replaceAll('\\', '/');

// 1. Código-fonte (fora dos testes): nenhum caminho de texto para HTML, script ou ambiente.
const PROIBIDOS = [
  [/dangerouslySetInnerHTML/, 'dangerouslySetInnerHTML (item 1)'],
  [/\.(innerHTML|outerHTML)\b/, 'innerHTML/outerHTML (item 1)'],
  [/insertAdjacentHTML/, 'insertAdjacentHTML (item 1)'],
  [/document\.write/, 'document.write (item 1)'],
  [/\beval\s*\(/, 'eval (item 1)'],
  [/new\s+Function\s*\(/, 'new Function (item 1)'],
  [/\bsrcDoc\b/, 'srcDoc (item 1)'],
  [/\bstyle=\{/, 'atributo style (item 2 e CSP)'],
];
const SO_EM_CONFIG = /import\.meta\.env/;

for (const arquivo of arquivos(SRC)) {
  if (!/\.(ts|tsx)$/.test(arquivo) || /\.test\.(ts|tsx)$/.test(arquivo) || arquivo.endsWith('.gen.ts')) {
    continue;
  }
  const linhas = readFileSync(arquivo, 'utf8').split('\n');
  linhas.forEach((linha, i) => {
    const texto = linha.trim();
    if (texto.startsWith('//') || texto.startsWith('*') || texto.startsWith('/*')) {
      return; // comentário
    }
    for (const [padrao, nome] of PROIBIDOS) {
      if (padrao.test(linha)) {
        problemas.push(`${rel(arquivo)}:${String(i + 1)}: ${nome}`);
      }
    }
    if (SO_EM_CONFIG.test(linha) && !arquivo.endsWith(join('src', 'api', 'config.ts'))) {
      problemas.push(`${rel(arquivo)}:${String(i + 1)}: import.meta.env fora de src/api/config.ts (item 4)`);
    }
  });
}

// 2. Build publicado.
let saida;
try {
  saida = arquivos(DIST);
} catch {
  console.error('dist/ não existe: rode `npx vite build` antes.');
  process.exit(1);
}
const api = loadEnv('production', RAIZ, 'VITE_').VITE_CONTAAI_API;

const html = readFileSync(join(DIST, 'index.html'), 'utf8');
const esperada = politicaDeSeguranca({ api, cabecalho: false }).replaceAll("'", '&#39;');
// HTML não diferencia maiúsculas (<SCRIPT> vale como <script>): toda busca de tag e atributo usa a flag i
// (alerta js/bad-tag-filter do CodeQL).
const metas = [...html.matchAll(/<meta\s+http-equiv\s*=\s*["']?Content-Security-Policy["']?\s+content\s*=\s*"([^"]*)"/gi)];
if (metas.length !== 1) {
  problemas.push(`dist/index.html: esperava 1 <meta> de CSP, achou ${String(metas.length)} (item 3)`);
} else {
  if (metas[0][1] !== esperada) {
    problemas.push('dist/index.html: a CSP do <meta> difere de csp.ts (item 3)');
  }
  const posicaoCsp = metas[0].index;
  const primeiroRecurso = html.search(/<script\b|<link\b[^>]*\brel\s*=\s*["']?stylesheet|<style\b/i);
  if (primeiroRecurso !== -1 && primeiroRecurso < posicaoCsp) {
    problemas.push('dist/index.html: há script ou estilo antes do <meta> da CSP, que só vale depois dele (item 3)');
  }
}

for (const arquivo of saida) {
  const nome = rel(arquivo);
  const ext = extname(arquivo);
  if (ext === '.map') {
    problemas.push(`${nome}: mapa de código no build`);
    continue;
  }
  if (!['.html', '.js', '.css'].includes(ext)) {
    continue;
  }
  const texto = readFileSync(arquivo, 'utf8');

  if (ext === '.html') {
    for (const tag of texto.matchAll(/<script\b[^>]*>/gi)) {
      if (!/\ssrc\s*=\s*["']\/(?!\/)[^"']*["']/i.test(tag[0])) {
        problemas.push(`${nome}: <script> sem src próprio: ${tag[0]} (item 3)`);
      }
    }
    if (/<style\b/i.test(texto)) problemas.push(`${nome}: <style> embutido (CSP style-src 'self')`);
    if (/\sstyle\s*=/i.test(texto)) problemas.push(`${nome}: atributo style (CSP style-src 'self')`);
    if (/\son[a-z]+\s*=/i.test(texto)) problemas.push(`${nome}: atributo de evento embutido (onclick etc.)`);
    for (const ref of texto.matchAll(/\s(?:src|href)\s*=\s*["']([^"']*)["']/gi)) {
      if (!ref[1].startsWith('/') || ref[1].startsWith('//')) {
        problemas.push(`${nome}: recurso fora do próprio endereço: ${ref[1]} (item 6)`);
      }
    }
  }

  if (ext === '.css') {
    for (const url of texto.matchAll(/url\(([^)]*)\)/g)) {
      const alvo = url[1].replace(/^["']|["']$/g, '');
      if (!alvo.startsWith('/') || alvo.startsWith('//')) {
        problemas.push(`${nome}: url() fora do próprio endereço: ${alvo} (item 6)`);
      }
    }
  }

  if (ext === '.js') {
    if (/sourceMappingURL/.test(texto)) problemas.push(`${nome}: referência a mapa de código`);
    // Endereços absolutos no código: só os nomes de espaço XML e os links de erro do React, que são texto
    // e não requisição. Qualquer outro é um terceiro em potencial (item 6).
    const PERMITIDOS = /^https?:\/\/(www\.w3\.org\/|react\.dev\/errors\/)/;
    for (const url of texto.matchAll(/https?:\/\/[a-zA-Z0-9.-]+[^\s"'`)]*/g)) {
      if (!PERMITIDOS.test(url[0]) && (api === undefined || !url[0].startsWith(api))) {
        problemas.push(`${nome}: endereço absoluto no código: ${url[0]} (item 6)`);
      }
    }
  }

  // Sem VITE_CONTAAI_API, o build publicado não pode apontar para a máquina de quem desenvolve.
  if (api === undefined && /127\.0\.0\.1|localhost/.test(texto)) {
    problemas.push(`${nome}: endereço local (127.0.0.1/localhost) no build publicado`);
  }
}

if (problemas.length > 0) {
  console.error(`Segurança da tela: ${String(problemas.length)} problema(s)`);
  for (const p of problemas) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`Segurança da tela: ok (${String(saida.length)} arquivos no dist/, CSP: ${politicaDeSeguranca({ api, cabecalho: false })})`);
