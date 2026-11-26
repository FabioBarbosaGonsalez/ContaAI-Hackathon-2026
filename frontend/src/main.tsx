import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './estilo/estilo.ts';
import { App } from './App.tsx';
import { api, iniciarSessao, sessaoEspaco, sessaoModo, sessaoToken } from './sessao/instancias.ts';

const raiz = document.getElementById('raiz');
if (raiz === null) {
  throw new Error('Elemento #raiz ausente no index.html');
}

void iniciarSessao();

createRoot(raiz).render(
  <StrictMode>
    <App sessao={{ api, espaco: sessaoEspaco, token: sessaoToken, modo: sessaoModo }} />
  </StrictMode>,
);
