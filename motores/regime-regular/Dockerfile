# syntax=docker/dockerfile:1
#
# Motor oficial da Receita Federal: calculadora-rtc-regime-regular (licença MIT).
# Fonte: https://github.com/ReceitaFederal/calculadora-rtc-regime-regular
#
# Versão fixada (princípio P5). Atualizar exige PR próprio e testes de referência verdes.
# O build busca o commit verificado pelo SHA, e não pela tag: em 2026-11-25 a Receita republicou a
# tag 1.7.2 do RR no commit 39363aa (remove ArredondamentoUtils.java e CaptchaException.java). O
# commit verificado em 2026-11-24 (32df719) continua no histórico oficial. Trocar de commit exige PR
# próprio e testes de referência verdes (ADR 0002).
#
# As etapas "fonte-rr" e "banco" são idênticas às do Dockerfile do Simples Nacional,
# para o BuildKit reaproveitar o banco gerado entre os dois builds.

ARG RR_TAG=1.7.2
ARG RR_SHA=32df7196356e81f2df08e6023fc2b6dbc48036d3

# ---------------------------------------------------------------------------
# Código-fonte do Regime Regular na tag fixada (tem o Flyway e os scripts SQL do banco).
# curl: o mvnw oficial baixa o maven-wrapper.jar com curl ou wget, e a imagem JDK não traz nenhum dos dois.
FROM eclipse-temurin:25-jdk AS fonte-rr
ARG RR_TAG
ARG RR_SHA
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src/rr
RUN git init -q . \
 && git remote add origin https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git \
 && git fetch -q --depth 1 origin "${RR_SHA}" \
 && git checkout -q --detach FETCH_HEAD \
 && atual="$(git rev-parse HEAD)" \
 && if [ "${atual}" != "${RR_SHA}" ]; then \
      echo "O commit baixado é ${atual}, esperado ${RR_SHA} (tag ${RR_TAG}). Abortando." >&2; exit 1; \
    fi

# ---------------------------------------------------------------------------
# Banco SQLite gerado pelo Flyway, como manda o README oficial (passo 3)
FROM fonte-rr AS banco
RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    mkdir -p calculadora/db \
 && ./mvnw flyway:migrate -Dflyway.configFiles=./flyway/flyway-pro.conf --batch-mode --errors --no-transfer-progress \
 && test -s calculadora/db/calculadora-pro.db

# ---------------------------------------------------------------------------
# JAR do motor (os testes do projeto oficial não rodam aqui; a conferência é o nosso make golden)
FROM fonte-rr AS build
RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    ./mvnw clean package -Dmaven.test.skip=true --batch-mode --errors --no-transfer-progress \
 && test -s target/api-regime-geral.jar

# ---------------------------------------------------------------------------
# Imagem final: só a JRE, o JAR e o banco somente leitura, com usuário sem privilégios
FROM eclipse-temurin:25-jre
ARG RR_TAG
LABEL org.opencontainers.image.title="contaai-motor-rr" \
      org.opencontainers.image.description="Calculadora RTC Regime Regular da Receita Federal, perfil offline" \
      org.opencontainers.image.version="${RR_TAG}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/ReceitaFederal/calculadora-rtc-regime-regular"
RUN groupadd --system motor && useradd --system --gid motor --no-create-home --shell /usr/sbin/nologin motor
# O perfil offline lê ./calculadora/db/calculadora-pro.db relativo ao diretório de trabalho
WORKDIR /app
COPY --from=build /src/rr/target/api-regime-geral.jar app.jar
COPY --from=banco /src/rr/calculadora/db/calculadora-pro.db calculadora/db/calculadora-pro.db
USER motor
EXPOSE 8080
# -XX:-UseBASE64Intrinsics: mitigação recomendada no CHANGELOG oficial (aviso OpenJDK de 2026-11-17)
ENTRYPOINT ["java", "-XX:-UseBASE64Intrinsics", "-XX:MaxRAMPercentage=75", \
            "-Dspring.profiles.active=offline", "-jar", "app.jar"]
# Saúde pela porta de gestão 9101 (application-offline.yml), sem instalar curl na imagem
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/9101 && printf 'GET /health HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n' >&3 && grep -q '\"UP\"' <&3"]
