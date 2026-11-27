// Notas de exemplo (C2c, ADR 0016): os XML fictícios de data/demo/notas, para quem avalia baixar e importar.
//
// Uma fonte só: o Vite acha os arquivos na pasta do repositório (a mesma das sementes e dos testes do backend) e,
// no build, copia cada um para o dist com um hash no nome. Nada é copiado à mão para dentro de frontend/. O
// vite.config.ts libera só essa pasta para o servidor de desenvolvimento e não deixa o XML virar data:.
//
// As frases vêm de data/demo/README.md e dos manifestos (sementes.json). Um teste confere que cada arquivo da
// pasta tem frase e que nenhuma frase fica sem arquivo.

const ENDERECOS = import.meta.glob<string>('../../../data/demo/notas/*.xml', {
  query: '?url',
  import: 'default',
  eager: true,
});

export interface NotaDeExemplo {
  /** O nome do arquivo na pasta, que é também o nome do download. */
  arquivo: string;
  /** O endereço do arquivo servido pela tela (no build, /assets/<nome>-<hash>.xml). */
  endereco: string;
  /** O que a nota mostra ao ser importada. */
  descricao: string;
}

/** Na ordem de interesse: a nota que gera o alerta, a dos itens sem par e a que já está na demonstração. */
export const DESCRICOES: readonly (readonly [arquivo: string, descricao: string])[] = [
  ['nfe-compra-2.xml', 'A cerveja sobe de R$ 2,60 para R$ 3,05 e gera um alerta de margem.'],
  ['nfe-item-sem-par.xml', 'Um item casa e dois ficam sem par: um código sem cadastro e uma NCM diferente.'],
  ['nfe-compra-1.xml', 'Já está na demonstração: importar de novo mostra o recibo gravado.'],
];

function nomeDoArquivo(caminho: string): string {
  return caminho.slice(caminho.lastIndexOf('/') + 1);
}

/** Os nomes dos arquivos que o Vite achou na pasta (para o teste comparar com as frases). */
export function arquivosNaPasta(enderecos: Record<string, string> = ENDERECOS): string[] {
  return Object.keys(enderecos).map(nomeDoArquivo).sort();
}

/** As notas de exemplo com frase e arquivo; uma frase sem arquivo fica de fora (o teste acusa). */
export function notasDeExemplo(enderecos: Record<string, string> = ENDERECOS): NotaDeExemplo[] {
  const porNome = new Map(Object.entries(enderecos).map(([caminho, endereco]) => [nomeDoArquivo(caminho), endereco]));
  return DESCRICOES.flatMap(([arquivo, descricao]) => {
    const endereco = porNome.get(arquivo);
    return endereco === undefined ? [] : [{ arquivo, endereco, descricao }];
  });
}
