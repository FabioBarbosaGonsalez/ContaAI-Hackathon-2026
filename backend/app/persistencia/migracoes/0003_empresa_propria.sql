-- C3-B (ADR 0017): a empresa própria.
--
-- 1. CNPJ alfanumérico. A Receita atribui o CNPJ alfanumérico às inscrições novas desde julho de 2026 (IN RFB
--    2.229/2024): 12 posições com dígitos ou letras maiúsculas e 2 dígitos verificadores numéricos. A NF-e o aceita
--    desde 01/07/2026 (NT 2026.004 v1.01). As tabelas com CHECK de CNPJ só numérico são reconstruídas.
--
--    Reconstrução pelo procedimento da documentação do SQLite (lang_altertable.html): tabela nova com nome
--    próprio, cópia, DROP da antiga e RENAME da nova. Banco.migrar desliga as chaves estrangeiras antes e roda
--    PRAGMA foreign_key_check antes do COMMIT: o DROP de `empresas` com elas ligadas apagaria em cascata os itens,
--    as notas e os clientes. Nenhuma das duas tabelas tem índice, gatilho ou visão além da chave primária.
--
--    GLOB é do SQLite. No PostgreSQL, o mesmo CHECK é `cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$'`.
--
-- 2. Item arquivado. Custos, preços, classificações e alertas são lançamentos que não mudam nem somem: apagar o item
--    apagaria esse histórico em cascata. O item sai do catálogo e o histórico fica.

CREATE TABLE empresas_0003 (
    cnpj          TEXT PRIMARY KEY CHECK (
                      length(cnpj) = 14 AND cnpj NOT GLOB '*[^0-9A-Z]*' AND substr(cnpj, 13) NOT GLOB '*[^0-9]*'
                  ),
    razao_social  TEXT NOT NULL,
    regime_atual  TEXT NOT NULL CHECK (regime_atual IN ('simples_tradicional', 'simples_hibrido')),
    empresa_json  TEXT NOT NULL,  -- app.dados_demo.Empresa, validado na leitura
    cenario_json  TEXT NOT NULL   -- app.dados_demo.Cenario (data e premissas rotuladas), validado na leitura
) STRICT;

INSERT INTO empresas_0003 (cnpj, razao_social, regime_atual, empresa_json, cenario_json)
    SELECT cnpj, razao_social, regime_atual, empresa_json, cenario_json FROM empresas;

DROP TABLE empresas;

ALTER TABLE empresas_0003 RENAME TO empresas;

CREATE TABLE clientes_b2b_0003 (
    cnpj          TEXT NOT NULL REFERENCES empresas (cnpj) ON DELETE CASCADE,  -- a empresa que vende
    cnpj_cliente  TEXT NOT NULL CHECK (
                      length(cnpj_cliente) = 14 AND cnpj_cliente NOT GLOB '*[^0-9A-Z]*'
                      AND substr(cnpj_cliente, 13) NOT GLOB '*[^0-9]*'
                  ),
    cliente_json  TEXT NOT NULL,  -- app.dados_demo.ClienteB2B, validado na leitura
    PRIMARY KEY (cnpj, cnpj_cliente)
) STRICT;

INSERT INTO clientes_b2b_0003 (cnpj, cnpj_cliente, cliente_json)
    SELECT cnpj, cnpj_cliente, cliente_json FROM clientes_b2b;

DROP TABLE clientes_b2b;

ALTER TABLE clientes_b2b_0003 RENAME TO clientes_b2b;

ALTER TABLE itens ADD COLUMN arquivado_em TEXT CHECK (arquivado_em IS NULL OR julianday(arquivado_em) IS NOT NULL);
