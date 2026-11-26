import { ProvedorSessao, type Sessao } from './sessao/contexto.tsx';
import { Shell } from './shell/Shell.tsx';

export function App({ sessao }: { sessao: Sessao }) {
  return (
    <ProvedorSessao sessao={sessao}>
      <Shell />
    </ProvedorSessao>
  );
}
