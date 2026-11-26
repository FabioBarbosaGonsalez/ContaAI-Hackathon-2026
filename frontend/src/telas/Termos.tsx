// Termos de uso (C2, T8; ADR 0016). Rascunho sem revisão jurídica.
//
// Cada regra citada vem do código: as da conta de REGRAS_DA_CONTA (conferidas com o backend em legal.test.ts), o
// aviso legal de shell/aviso.ts. Responsável: "Equipe ContaAI", sem e-mail e sem nome (plano v2.1, C2, decisão 4).
// Mudar este texto pede uma versão nova em legal.ts e em backend/app/contas/termos.py.

import { AVISO_LEGAL } from '../shell/aviso.ts';
import { Link } from '../shell/navegacao.tsx';
import { REGRAS_DA_CONTA as R, VERSAO_TERMOS, dataDaVersao } from './legal.ts';
import { TextoLegal } from './TextoLegal.tsx';

export function Termos() {
  return (
    <TextoLegal
      titulo="Termos de uso"
      subtitulo={`Versão de ${dataDaVersao(VERSAO_TERMOS)}`}
      outro={{ para: '/privacidade', nome: 'Privacidade' }}
      secoes={[
        {
          id: 'termos-o-que-e',
          titulo: 'O que é o ContaAI',
          conteudo: (
            <>
              <p>
                O ContaAI estima, para a pequena empresa do Simples Nacional, os tributos da reforma (CBS, IBS e Imposto
                Seletivo) de cada item que ela vende, o preço que mantém a margem e a diferença entre o Simples tradicional
                e o híbrido. As contas vêm das calculadoras oficiais da Receita Federal.
              </p>
              <p>{AVISO_LEGAL}</p>
              <p>
                De 2027 em diante, as alíquotas são premissas, e o resultado é uma simulação. Decida preço e regime com o
                seu contador.
              </p>
            </>
          ),
        },
        {
          id: 'termos-demonstracao',
          titulo: 'A demonstração',
          conteudo: (
            <>
              <p>A demonstração não pede cadastro. A empresa, as notas de compra e o cliente dela são fictícios.</p>
              <p>
                A demonstração compartilhada é igual para todos. O espaço próprio é uma cópia dos dados fictícios que vence
                no prazo mostrado na barra e depois é apagada.
              </p>
              <p>Não ponha dados reais na demonstração nem no espaço.</p>
            </>
          ),
        },
        {
          id: 'termos-conta',
          titulo: 'A conta',
          conteudo: (
            <>
              <p>
                Para criar uma conta, você informa um e-mail, uma senha de pelo menos {R.senhaMinima} caracteres e o nome da
                sua organização, e aceita estes termos.
              </p>
              <p>
                O ContaAI não envia mensagem para confirmar o e-mail. Use um e-mail seu: criar uma conta com o e-mail de
                outra pessoa não é permitido.
              </p>
              <p>
                A conta exige um segundo fator: o código de {R.digitosDoCodigo} dígitos de um aplicativo autenticador. No
                cadastro, você recebe {R.codigosDeRecuperacao} códigos de recuperação, e cada um vale uma vez só.
              </p>
              <p>
                Não há recuperação de senha. Se você perder a senha, ou o aplicativo e todos os códigos de recuperação,
                perde o acesso à conta.
              </p>
              <p>
                Depois de {R.falhasParaEsperar} tentativas erradas seguidas, é preciso esperar antes de tentar de novo:{' '}
                {R.esperaInicialS} segundos, o dobro a cada novo erro, até {R.esperaMaximaS / 3600} hora. Depois de{' '}
                {R.falhasParaBloquear} tentativas erradas seguidas, a conta é bloqueada.
              </p>
              <p>
                A sessão termina depois de {R.sessaoOciosaMin} minutos sem uso, ou {R.sessaoTotalH} horas depois de entrar.
              </p>
            </>
          ),
        },
        {
          id: 'termos-organizacao',
          titulo: 'A organização',
          conteudo: (
            <>
              <p>Quem cria a conta é dono da organização que informou no cadastro.</p>
              <p>
                Você pode excluir a conta a qualquer momento, com a senha. Se você for a única pessoa da organização, a
                organização e os dados dela são apagados junto. Se houver outros membros e você for o único dono, passe a posse a
                um deles antes.
              </p>
            </>
          ),
        },
        {
          id: 'termos-proibido',
          titulo: 'O que não é permitido',
          conteudo: (
            <>
              <ul>
                <li>Entrar na conta de outra pessoa ou tentar ver os dados de outra organização.</li>
                <li>Contornar os limites de tentativas e de uso.</li>
                <li>Usar dados reais de terceiros na demonstração.</li>
              </ul>
            </>
          ),
        },
        {
          id: 'termos-mudancas',
          titulo: 'Mudanças nestes termos',
          conteudo: (
            <>
              <p>
                Quando o texto mudar, a versão muda. A versão que você aceitou fica gravada na sua conta, com a data do
                aceite. O que acontece com os dados está na <Link para="/privacidade">política de privacidade</Link>.
              </p>
            </>
          ),
        },
        {
          id: 'termos-responsavel',
          titulo: 'Quem responde',
          conteudo: (
            <>
              <p>Equipe ContaAI.</p>
            </>
          ),
        },
      ]}
    />
  );
}
