# ADR 0002 — Motores oficiais em containers próprios

- Status: aceito
- Data: 2026-11-24
- Etapa: E0-01 e E0-02

## Contexto

Os dois motores exigem Java 25 (`<java.version>25</java.version>` nos `pom.xml` das tags `1.7.2` e `1.0.2`) e um banco SQLite gerado pelo Flyway antes da primeira execução. Não há Dockerfile oficial em nenhum dos repositórios. As máquinas do time não têm, necessariamente, JDK 25 nem Maven.

## Decisão

- Um Dockerfile multi-stage por motor (`motores/regime-regular`, `motores/simples-nacional`), baseado em `eclipse-temurin:25-jdk` para compilar e `eclipse-temurin:25-jre` para rodar. Ninguém precisa instalar Java.
- O código vem do GitHub da Receita na tag fixada, e o build **falha se a tag não apontar para o commit verificado** (`RR_SHA`, `SN_SHA`).
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
