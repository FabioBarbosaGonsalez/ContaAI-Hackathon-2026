// Barreira de erro por página: se uma tela quebra ao desenhar (uma resposta da API num formato que a tela
// não esperava, por exemplo), só ela mostra o aviso. A barra, o menu e o rodapé continuam funcionando, e
// trocar de página tenta de novo (o Shell troca a `key` a cada caminho).
//
// O texto do erro não é exibido: pode trazer detalhes internos, e a pessoa não tem o que fazer com ele.

import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface Estado {
  quebrou: boolean;
}

export class BarreiraDeErro extends Component<Props, Estado> {
  override state: Estado = { quebrou: false };

  static getDerivedStateFromError(): Estado {
    return { quebrou: true };
  }

  override componentDidCatch(erro: Error, info: ErrorInfo): void {
    // Só no console do navegador de quem usa; nada sai da página.
    console.error('A tela quebrou ao desenhar', erro, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.quebrou) {
      return (
        <div className="pagina__cabecalho" role="alert">
          <h1>Não foi possível mostrar esta tela</h1>
          <p className="pagina__subtitulo">
            A API respondeu num formato que a tela não reconhece. As outras telas continuam disponíveis no menu;
            recarregar a página tenta de novo.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
