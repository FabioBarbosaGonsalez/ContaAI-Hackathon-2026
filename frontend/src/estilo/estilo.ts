// Fontes e estilos globais, carregados uma vez no main.tsx.
//
// As fontes Geist e Geist Mono (SIL Open Font License 1.1) vêm dos pacotes @fontsource-variable e entram no
// build junto do app: nenhuma requisição ao Google Fonts ou a CDN (LGPD; docs/seguranca.md, regras da
// interface, item 6). Cada @font-face tem unicode-range, então o navegador só baixa os arquivos dos
// caracteres em uso, os do alfabeto latino.
import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import './tokens.css';
import './base.css';
