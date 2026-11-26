// Lint do frontend (ESLint 9 em flat config).
// O ESLint fica na 9, porque eslint-plugin-react 7.37.5 e eslint-plugin-jsx-a11y 6.10.2 só aceitam ESLint até a 9.
// A 9 está em fim de vida desde 2026-08-06 (eslint.org/version-support). Ela só roda no desenvolvimento e no CI,
// e o npm audit do CI acusa se aparecer vulnerabilidade nela. Migrar para a 10 quando o jsx-a11y aceitar a 10.
import js from '@eslint/js';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// Regras de segurança da tela (docs/seguranca.md, regras da interface). Cada uma barra um padrão no código:
const XSS_HTML = [
  {
    selector: "MemberExpression[property.name=/^(innerHTML|outerHTML)$/]",
    message: 'Item 1: texto vira HTML. Mostre como texto (o React já escapa).',
  },
  {
    selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
    message: 'Item 1: texto vira HTML. Mostre como texto (o React já escapa).',
  },
  {
    selector: "CallExpression[callee.object.name='document'][callee.property.name=/^(write|writeln)$/]",
    message: 'Item 1: document.write é proibido.',
  },
  {
    selector: "JSXAttribute[name.name='srcDoc']",
    message: 'Item 1: srcDoc monta HTML a partir de texto.',
  },
];
const URL_DE_DADO = {
  // Um texto da API nunca vira endereço: só o Link (src/shell/navegacao.tsx) monta href, a partir das rotas fixas.
  selector:
    "JSXAttribute[name.name=/^(href|src|action|formAction|xlinkHref|poster|data)$/][value.type='JSXExpressionContainer']",
  message: 'Item 2: endereço montado de um valor. Use o Link com uma rota fixa, ou um texto literal.',
};
const ESTILO_EM_LINHA = {
  // A CSP é style-src 'self'; e um texto da API nunca vira estilo.
  selector: "JSXAttribute[name.name='style']",
  message: 'Item 2 e CSP: sem atributo style. Use uma classe no CSS.',
};
const VARIAVEL_DE_AMBIENTE = {
  // Toda VITE_* vai para o navegador; só src/api/config.ts lê o ambiente, e só o endereço da API.
  selector: "MemberExpression[object.type='MetaProperty'][property.name='env']",
  message: 'Item 4: import.meta.env só em src/api/config.ts.',
};

export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.strictTypeChecked,
      react.configs.flat.recommended,
      react.configs.flat['jsx-runtime'],
      reactHooks.configs.flat.recommended,
      jsxA11y.flatConfigs.strict,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // Regras de XSS da tela (docs/seguranca.md, regras da interface, item 1).
      'react/no-danger': 'error',
      'react/no-danger-with-children': 'error',
      'react/jsx-no-script-url': 'error',
      'react/jsx-no-target-blank': 'error',
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-script-url': 'error',
      'no-restricted-syntax': ['error', ...XSS_HTML, URL_DE_DADO, ESTILO_EM_LINHA, VARIAVEL_DE_AMBIENTE],
    },
  },
  {
    // O Link é o único lugar que monta href, e só com um Caminho das rotas fixas (tipado).
    files: ['src/shell/navegacao.tsx'],
    rules: { 'no-restricted-syntax': ['error', ...XSS_HTML, ESTILO_EM_LINHA, VARIAVEL_DE_AMBIENTE] },
  },
  {
    files: ['src/api/config.ts'],
    rules: { 'no-restricted-syntax': ['error', ...XSS_HTML, URL_DE_DADO, ESTILO_EM_LINHA] },
  },
  {
    // Arquivos que rodam no Node (configuração e roteiros), não no navegador.
    files: ['vite.config.ts', 'csp.ts', 'eslint.config.js', 'scripts/**/*.mjs'],
    languageOptions: { globals: globals.node },
    rules: { 'no-restricted-syntax': 'off' },
  },
  {
    files: ['eslint.config.js', 'scripts/**/*.mjs'],
    extends: [js.configs.recommended, tseslint.configs.disableTypeChecked],
  },
);
