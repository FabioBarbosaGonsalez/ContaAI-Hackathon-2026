# ADR 0002 — Motores oficiais em containers próprios

- Status: aceito
- Data: 2026-11-24
- Etapa: E0-01 e E0-02

## Contexto

Os dois motores exigem Java 25 (`<java.version>25</java.version>` nos `pom.xml` das tags `1.7.2` e `1.0.2`) e um banco SQLite gerado pelo Flyway antes da primeira execução. Não há Dockerfile oficial em nenhum dos repositórios. As máquinas do time não têm, necessariamente, JDK 25 nem Maven.

## Decisão

- Um Dockerfile multi-stage por motor (`motores/regime-regular`, `motores/simples-nacional`), baseado em `eclipse-temurin:25-jdk` para compilar e `eclipse-temurin:25-jre` para rodar. Ninguém precisa instalar Java.
- O código vem do GitHub da Receita na tag fixada, e o build **falha se a tag não apontar para o commit verificado** (`RR_SHA`, `SN_SHA`). **Atualizado em 2026-11-25:** o build passou a buscar o commit verificado pelo SHA (`git fetch origin <SHA>`), e não mais pela tag, porque a Receita republicou a tag `1.7.2` do RR (ver abaixo).
- O banco é gerado com o comando do README oficial (`mvnw flyway:migrate -Dflyway.configFiles=./flyway/flyway-pro.conf`) a partir do repositório do Regime Regular, como manda o README do Simples Nacional. As etapas `fonte-rr` e `banco` são idênticas nos dois Dockerfiles, e o BuildKit gera o banco uma vez só.
- A JVM roda com `-XX:-UseBASE64Intrinsics`, mitigação indicada nos CHANGELOGs oficiais (aviso de segurança do OpenJDK de 2026-11-17).
- A imagem final roda com usuário de sistema sem privilégios (`motor`) e o banco é aberto em modo somente leitura (`mode=ro` no `application-offline.yml` oficial).
- O healthcheck usa a porta de gestão (`9101` no RR, `9103` no SN, rota `/health`) por `/dev/tcp` do bash, sem instalar `curl` na imagem final.

## Segurança

- Os motores liberam todas as rotas sem autenticação (`anyRequest().permitAll()` no `WebSecurityConfig` oficial). Por isso o `docker-compose.yml` publica as portas **só em 127.0.0.1**, e as portas de gestão não são publicadas. No deploy, só o backend fala com os motores, pela rede interna do Compose.
- `GET /versao/status` (e a subida dos dois motores) consulta a versão da instalação online da Receita em `piloto-cbs.tributos.gov.br`. A chamada não envia dados de operação; se a rede não responder, o motor segue funcionando (CHANGELOG 1.7.2 do RR). A URL pode ser trocada por `VERSAO_OFFLINE_URL` (RR) e `VERSAO_URL` (SN).

## Conferência de versão

- `GET /versao/status` não serve para conferir a versão do SN. A URL padrão dele (`VERSAO_URL` no `application-offline.yml`) aponta para a mesma rota da instalação online do RR (`.../api/calculadora/dados-abertos/versao`), e a resposta compara `1.0.2` com `1.7.2`, devolvendo `aplicacaoAtualizada: false` mesmo na versão mais recente publicada (verificado em 2026-11-24).
- Por isso o plano ("/versao/status na inicialização", P5) é cumprido de outra forma: cada resposta de cálculo traz `X-CALC-APP-VERSION` e `X-CALC-DB-VERSION`, e quem confere são os testes de referência (contra o `ARG` do Dockerfile) e, na Etapa 1, o `GET /saude` do backend, sempre contra as tags fixadas.

## Custos

Tudo gratuito: imagens Eclipse Temurin (Adoptium), Maven Central e o código MIT da Receita. O Docker Desktop é gratuito para uso pessoal, educação, projetos open source não comerciais e empresas com menos de 250 funcionários **e** menos de US$ 10 milhões de receita anual; órgãos de governo precisam de assinatura ([licença do Docker Desktop](https://docs.docker.com/subscription-billing/desktop-license/), consultada em 2026-11-24).

## Consequências

- Primeira subida: alguns minutos (dependências Maven e banco). As seguintes usam o cache.
- Trocar a versão de um motor exige mudar `*_TAG` e `*_SHA`, regravar os testes de referência (`make gravar-golden`) e revisar a diferença num PR próprio (P5).

## Tag 1.7.2 republicada pela Receita (2026-11-25)

- **O que aconteceu:** o golden do PR #5 falhou no build do motor RR: "A tag 1.7.2 aponta para 39363aa…, esperado 32df719…". A trava funcionou.
- **Conferido na API do GitHub:** a release 1.7.2 foi republicada em 2026-11-25 às 13:44 (UTC) pelo mesmo robô de CI das releases anteriores, com a mesma mensagem ("release: calculadora-rtc-regime-regular 1.7.2"). O commit novo vem 2 à frente do verificado, sem nenhum atrás, e só remove dois arquivos:
  - `src/main/java/br/gov/serpro/rtc/core/util/ArredondamentoUtils.java` (198 linhas);
  - `src/main/java/br/gov/serpro/rtc/domain/service/exception/CaptchaException.java`.
- **O que decidimos:** os Dockerfiles passam a baixar o commit verificado (32df719) pelo SHA. O build volta a ser idêntico ao testado, sem aceitar uma tag que mudou depois da verificação. Imagens reconstruídas do zero (`--no-cache`), com 46 golden verdes. O motor SN (tag 1.0.2, commit f90b652) não mudou e também passou a ser baixado pelo SHA.
- **Em aberto:** adotar o commit novo da 1.7.2 exige um PR próprio, com os testes de referência regravados e conferidos (P5). A remoção de um utilitário de arredondamento merece essa conferência antes, mesmo que o código removido pareça não ser usado.

