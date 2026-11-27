// Política de privacidade (C2, T8; ADR 0016). Rascunho sem revisão jurídica.
//
// Fontes lidas em 2026-11-26:
// - LGPD (Lei nº 13.709/2018), no Planalto: art. 5º (definições), 7º (bases legais; o inciso V é a execução de
//   contrato a pedido do titular), 9º (o que informar ao titular), 18 (direitos) e 41 (encarregado);
// - ANPD, "Guia orientativo: cookies e proteção de dados pessoais" (out/2022): cookies necessários (p. 10), o
//   consentimento não é a base adequada para os estritamente necessários (p. 20), e a política de cookies pode
//   ser uma seção da política de privacidade, com finalidade, retenção e compartilhamento (p. 28-29).
//
// Cada dado guardado vem das migrações de backend/app/contas/migracoes e, os da empresa (C3a, ADR 0018), de
// backend/app/persistencia/migracoes; os prazos, de REGRAS_DA_CONTA e de COOKIES (conferidos com o backend em
// legal.test.ts). O id do espaço, de sessao/espaco.ts. O que vai às calculadoras, de
// backend/app/motores/requisicoes.py (os itens, a data, a UF, o município e a atividade).
//
// Risco registrado no plano v2.1 (C2, decisão 4): o art. 9º, III e IV, e o art. 41, § 1º, pedem o contato do
// controlador e do encarregado. A página mostra só "Equipe ContaAI", por decisão do usuário; rever antes da E6.

import { CHAVE_ARMAZENAMENTO_ESPACO } from '../sessao/espaco.ts';
import { Link } from '../shell/navegacao.tsx';
import { ATUALIZACAO_PRIVACIDADE, COOKIES, REGRAS_DA_CONTA as R, dataDaVersao } from './legal.ts';
import { TextoLegal } from './TextoLegal.tsx';

export function Privacidade() {
  return (
    <TextoLegal
      titulo="Privacidade"
      subtitulo={`Atualizada em ${dataDaVersao(ATUALIZACAO_PRIVACIDADE)}`}
      outro={{ para: '/termos', nome: 'Termos de uso' }}
      secoes={[
        {
          id: 'privacidade-quem',
          titulo: 'Quem responde pelos dados',
          conteudo: (
            <>
              <p>Equipe ContaAI.</p>
            </>
          ),
        },
        {
          id: 'privacidade-demonstracao',
          titulo: 'Na demonstração, sem conta',
          conteudo: (
            <>
              <p>A demonstração não pede nenhum dado pessoal.</p>
              <p>
                Quando você cria um espaço próprio, o navegador guarda o identificador do espaço no armazenamento local
                (<code>localStorage</code>, chave <code>{CHAVE_ARMAZENAMENTO_ESPACO}</code>). É um código sorteado, sem dado
                pessoal, que abre o mesmo espaço em outra aba. Ele é apagado quando você sai do espaço ou quando o espaço
                vence.
              </p>
            </>
          ),
        },
        {
          id: 'privacidade-conta',
          titulo: 'Com conta: o que fica guardado',
          conteudo: (
            <>
              <ul>
                <li>o e-mail e o nome da organização;</li>
                <li>a senha, só como resumo Argon2id: a senha em si não é guardada;</li>
                <li>o segredo do segundo fator, para conferir os códigos do aplicativo;</li>
                <li>os códigos de recuperação, só como resumo SHA-256;</li>
                <li>as sessões abertas: só o resumo do token, o início, o último uso e o vencimento;</li>
                <li>quantas tentativas erradas seguidas houve, e a espera ou o bloqueio;</li>
                <li>avisos de segurança, como “código de recuperação usado”: só o tipo e a data, sem IP e sem navegador;</li>
                <li>a versão dos termos que você aceitou e a data do aceite.</li>
              </ul>
              <p>Quando você cadastra a empresa, ficam guardados também, no espaço da sua organização:</p>
              <ul>
                <li>o CNPJ, a razão social, o regime no Simples, a UF, o município e a atividade;</li>
                <li>os itens do catálogo, os preços, os custos, as classificações e os alertas;</li>
                <li>
                  das notas de compra importadas: o emitente, a série, o número, a data, o resumo SHA-256 do arquivo e o
                  recibo da importação. O arquivo XML não é guardado: guarde as suas notas, porque o ContaAI não é o seu
                  arquivo fiscal;
                </li>
                <li>os clientes empresa: o CNPJ, a razão social, o regime, o local e a compra mensal.</li>
              </ul>
              <p>
                Os dados da conta servem só para criar a conta, deixar você entrar e proteger a conta; os da empresa, para
                os cálculos que você pede. A base legal é a execução do contrato que os{' '}
                <Link para="/termos">termos de uso</Link> formam, a seu pedido (LGPD, art. 7º, V).
              </p>
            </>
          ),
        },
        {
          id: 'privacidade-cookies',
          titulo: 'Cookies',
          conteudo: (
            <>
              <p>O ContaAI usa dois cookies, só depois que você começa a entrar ou a criar a conta:</p>
              <div className="tabela__moldura">
                <table className="tabela legal__tabela">
                  <thead>
                    <tr>
                      <th scope="col">Cookie</th>
                      <th scope="col">Para quê</th>
                      <th scope="col">Quanto tempo</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>
                        <code>{COOKIES.sessao}</code>
                      </td>
                      <td>Mantém você conectado.</td>
                      <td>
                        Até {R.sessaoOciosaMin} minutos sem uso, ou {R.sessaoTotalH} horas depois de entrar. Sair apaga.
                      </td>
                    </tr>
                    <tr>
                      <td>
                        <code>{COOKIES.passe}</code>
                      </td>
                      <td>Guarda a etapa entre a senha e o código, ou entre o cadastro e a confirmação do segundo fator.</td>
                      <td>{R.passeMin} minutos.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p>
                Os dois são <code>HttpOnly</code> (o código da página não os lê), <code>Secure</code> (só andam por
                conexão segura) e <code>SameSite=Strict</code> (outro site não os envia). São estritamente necessários: sem
                eles não dá para entrar. Por isso não há pedido de consentimento para eles, como orienta o guia de cookies
                da ANPD (2022).
              </p>
              <p>O ContaAI não usa cookies de análise, de publicidade nem de terceiros.</p>
            </>
          ),
        },
        {
          id: 'privacidade-registros',
          titulo: 'Registros técnicos',
          conteudo: (
            <>
              <p>
                O banco de dados da conta não guarda o endereço IP. O limite de pedidos por IP fica só na memória do
                servidor e some quando ele reinicia. O log técnico da API registra, de cada pedido, só o tipo, a rota sem
                os dados dela (por exemplo, <code>/empresas/{'{cnpj}'}</code>, nunca o CNPJ), o resultado e quanto tempo
                levou: sem o IP e sem dado pessoal. Um erro inesperado entra no log só com o tipo e o lugar do código
                onde aconteceu, sem a mensagem.
              </p>
            </>
          ),
        },
        {
          id: 'privacidade-compartilhamento',
          titulo: 'Com quem os dados são compartilhados',
          conteudo: (
            <>
              <p>
                Com ninguém. As calculadoras oficiais rodam no próprio servidor do ContaAI e recebem só os dados dos itens e
                da operação (a data, a UF, o município e a atividade), nunca o CNPJ, a razão social ou um dado pessoal.
              </p>
            </>
          ),
        },
        {
          id: 'privacidade-tempo',
          titulo: 'Por quanto tempo',
          conteudo: (
            <>
              <ul>
                <li>A conta e os dados dela: até você excluir a conta.</li>
                <li>
                  A empresa e os dados dela: enquanto a organização existir. A exclusão da conta da única pessoa da
                  organização apaga a organização e tudo o que ela guarda.
                </li>
                <li>
                  Um cadastro sem o segundo fator confirmado: deixa de valer {R.pendenteMin} minutos depois do cadastro, ou
                  da última entrada com a senha, e depois é apagado.
                </li>
                <li>As sessões e as etapas de entrada: apagadas depois de vencer.</li>
              </ul>
            </>
          ),
        },
        {
          id: 'privacidade-direitos',
          titulo: 'Os seus direitos',
          conteudo: (
            <>
              <p>
                A LGPD (art. 18) garante, entre outros, confirmar que os seus dados são tratados, ter acesso a eles e pedir
                a eliminação. No ContaAI:
              </p>
              <ul>
                <li>ver os seus dados: em “Sua conta”, no menu da conta (o botão com o seu e-mail, na barra);</li>
                <li>
                  excluir a conta: em “Sua conta”, com a senha. A exclusão apaga a conta na hora e, se você for a única
                  pessoa da organização, também a organização e os dados dela.
                </li>
              </ul>
            </>
          ),
        },
      ]}
    />
  );
}
