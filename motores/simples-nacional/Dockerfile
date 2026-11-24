# syntax=docker/dockerfile:1
#
# Motor oficial da Receita Federal: calculadora-rtc-simples-nacional (licença MIT).
# Fonte: https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional
#
# O README oficial manda gerar o banco com os scripts do repositório do Regime Regular;
# por isso este build também baixa o RR na tag fixada. Versões fixadas (princípio P5).
#
# As etapas "fonte-rr" e "banco" são idênticas às do Dockerfile do Regime Regular,
# para o BuildKit reaproveitar o banco gerado entre os dois builds.

ARG RR_TAG=1.7.2
ARG RR_SHA=32df7196356e81f2df08e6023fc2b6dbc48036d3
ARG SN_TAG=1.0.2
ARG SN_SHA=f90b6525e6d5823e784baecfc6fef0ad2f04b74f

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
RUN git clone --depth 1 --branch "${RR_TAG}" \
      https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git . \
 && atual="$(git rev-parse HEAD)" \
 && if [ "${atual}" != "${RR_SHA}" ]; then \
      echo "A tag ${RR_TAG} aponta para ${atual}, esperado ${RR_SHA}. Abortando." >&2; exit 1; \
    fi

# ---------------------------------------------------------------------------
# Banco SQLite gerado pelo Flyway, como manda o README oficial (passo 3)
FROM fonte-rr AS banco
RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    mkdir -p calculadora/db \
 && ./mvnw flyway:migrate -Dflyway.configFiles=./flyway/flyway-pro.conf --batch-mode --errors --no-transfer-progress \
 && test -s calculadora/db/calculadora-pro.db

# ---------------------------------------------------------------------------
# Código-fonte e JAR do Simples Nacional na tag fixada
FROM fonte-rr AS build
ARG SN_TAG
ARG SN_SHA
WORKDIR /src/sn
RUN git clone --depth 1 --branch "${SN_TAG}" \
      https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional.git . \
 && atual="$(git rev-parse HEAD)" \
 && if [ "${atual}" != "${SN_SHA}" ]; then \
      echo "A tag ${SN_TAG} aponta para ${atual}, esperado ${SN_SHA}. Abortando." >&2; exit 1; \
    fi
RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    ./mvnw clean package -Dmaven.test.skip=true --batch-mode --errors --no-transfer-progress \
 && test -s target/api-simples-nacional.jar

# ---------------------------------------------------------------------------
# Imagem final: só a JRE, o JAR e o banco somente leitura, com usuário sem privilégios
FROM eclipse-temurin:25-jre
ARG SN_TAG
LABEL org.opencontainers.image.title="contaai-motor-sn" \
      org.opencontainers.image.description="Calculadora RTC Simples Nacional da Receita Federal, perfil offline" \
      org.opencontainers.image.version="${SN_TAG}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional"
RUN groupadd --system motor && useradd --system --gid motor --no-create-home --shell /usr/sbin/nologin motor
# O perfil offline lê ./calculadora/db/calculadora-pro.db relativo ao diretório de trabalho
WORKDIR /app
COPY --from=build /src/sn/target/api-simples-nacional.jar app.jar
COPY --from=banco /src/rr/calculadora/db/calculadora-pro.db calculadora/db/calculadora-pro.db
USER motor
EXPOSE 8082
# -XX:-UseBASE64Intrinsics: mitigação recomendada no CHANGELOG oficial (aviso OpenJDK de 2026-11-17)
ENTRYPOINT ["java", "-XX:-UseBASE64Intrinsics", "-XX:MaxRAMPercentage=75", \
            "-Dspring.profiles.active=offline", "-jar", "app.jar"]
# Saúde pela porta de gestão 9103 (application-offline.yml), sem instalar curl na imagem
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/9103 && printf 'GET /health HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n' >&3 && grep -q '\"UP\"' <&3"]
