-- 0001: esquema inicial da E4 (ADR 0008).
--
-- Regras:
-- - Toda tabela de dados de contribuinte tem o CNPJ (ADR 0004, item 5; painel do contador, D1).
-- - Dinheiro, quantidades e percentuais ficam como TEXTO decimal ("3.05"), nunca REAL (sem erro de ponto
--   flutuante). Datas e horas em ISO 8601 com fuso: instantes do sistema em UTC; datas do documento (emissão
--   da nota) com o fuso da nota, ordenadas por julianday(), que converte o fuso. O CHECK recusa data inválida.
-- - Custos e preços são lançamentos: só acréscimo. O custo atual é o da nota mais recente (por data de
--   emissão, depois por id); o preço atual é o último lançado (por id). Os gatilhos impedem alterar um
--   lançamento, e nenhum código apaga. A restauração das sementes monta um banco novo e substitui o
--   conteúdo inteiro deste (API de backup do SQLite).
-- - Este arquivo não muda depois de aplicado (o hash fica em schema_migrations). Mudança = nova migração.

CREATE TABLE empresas (
    cnpj          TEXT PRIMARY KEY CHECK (length(cnpj) = 14 AND cnpj NOT GLOB '*[^0-9]*'),
    razao_social  TEXT NOT NULL,
    regime_atual  TEXT NOT NULL CHECK (regime_atual IN ('simples_tradicional', 'simples_hibrido')),
    empresa_json  TEXT NOT NULL,  -- app.dados_demo.Empresa, validado na leitura
    cenario_json  TEXT NOT NULL   -- app.dados_demo.Cenario (data e premissas rotuladas), validado na leitura
) STRICT;

CREATE TABLE itens (
    cnpj        TEXT NOT NULL REFERENCES empresas (cnpj) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,
    ncm         TEXT NOT NULL,
    unidade     TEXT NOT NULL,
    item_json   TEXT NOT NULL,  -- app.dados_demo.ItemCatalogo (classificação e fontes), validado na leitura
    PRIMARY KEY (cnpj, item_id)
) STRICT;

-- Código do produto no fornecedor (cProd). Só é único dentro de um fornecedor.
CREATE TABLE codigos_fornecedor (
    cnpj             TEXT NOT NULL,
    cnpj_fornecedor  TEXT NOT NULL,
    codigo           TEXT NOT NULL,
    item_id          TEXT NOT NULL,
    PRIMARY KEY (cnpj, cnpj_fornecedor, codigo),
    FOREIGN KEY (cnpj, item_id) REFERENCES itens (cnpj, item_id) ON DELETE CASCADE
) STRICT;

CREATE TABLE notas (
    id               INTEGER PRIMARY KEY,
    cnpj             TEXT NOT NULL REFERENCES empresas (cnpj) ON DELETE CASCADE,  -- destinatário
    cnpj_emitente    TEXT NOT NULL,
    serie            TEXT NOT NULL,
    numero           TEXT NOT NULL,
    data_emissao     TEXT NOT NULL CHECK (julianday(data_emissao) IS NOT NULL),  -- como na nota
    sha256           TEXT NOT NULL,  -- do arquivo recebido: a mesma nota com outro conteúdo é recusada
    importada_em     TEXT NOT NULL CHECK (julianday(importada_em) IS NOT NULL),  -- UTC
    recibo_json      TEXT NOT NULL,  -- resposta da importação, devolvida de novo se a nota vier outra vez
    UNIQUE (cnpj, cnpj_emitente, serie, numero)
) STRICT;

CREATE TABLE custos (
    id                INTEGER PRIMARY KEY,
    cnpj              TEXT NOT NULL,
    item_id           TEXT NOT NULL,
    nota_id           INTEGER NOT NULL REFERENCES notas (id) ON DELETE CASCADE,
    data              TEXT NOT NULL CHECK (julianday(data) IS NOT NULL),  -- emissão da nota, com o fuso dela
    quantidade        TEXT NOT NULL,
    custo_unitario    TEXT NOT NULL,  -- vUnCom
    credito_unitario  TEXT,           -- CBS + IBS da compra por unidade; NULL se não foi possível obter
    fonte_credito     TEXT CHECK (fonte_credito IN ('nfe', 'motor')),
    FOREIGN KEY (cnpj, item_id) REFERENCES itens (cnpj, item_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX custos_por_item ON custos (cnpj, item_id, julianday(data), id);

CREATE TABLE alertas (
    id           TEXT PRIMARY KEY,
    cnpj         TEXT NOT NULL,
    item_id      TEXT NOT NULL,
    nota_id      INTEGER NOT NULL REFERENCES notas (id) ON DELETE CASCADE,
    criado_em    TEXT NOT NULL CHECK (julianday(criado_em) IS NOT NULL),  -- UTC
    alerta_json  TEXT NOT NULL,  -- app.contrato.Alerta no momento da criação (não muda)
    aplicado_em  TEXT CHECK (aplicado_em IS NULL OR julianday(aplicado_em) IS NOT NULL),  -- UTC
    FOREIGN KEY (cnpj, item_id) REFERENCES itens (cnpj, item_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX alertas_por_empresa ON alertas (cnpj, criado_em);

CREATE TABLE precos (
    id              INTEGER PRIMARY KEY,
    cnpj            TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    valor_unitario  TEXT NOT NULL,  -- vUnCom de venda
    vigente_desde   TEXT NOT NULL CHECK (julianday(vigente_desde) IS NOT NULL),  -- UTC
    origem          TEXT NOT NULL CHECK (origem IN ('semente', 'alerta')),
    alerta_id       TEXT REFERENCES alertas (id) ON DELETE CASCADE,
    FOREIGN KEY (cnpj, item_id) REFERENCES itens (cnpj, item_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX precos_por_item ON precos (cnpj, item_id, vigente_desde, id);

CREATE TRIGGER custos_sem_alteracao BEFORE UPDATE ON custos
BEGIN
    SELECT RAISE(ABORT, 'lançamento de custo não se altera');
END;

CREATE TRIGGER precos_sem_alteracao BEFORE UPDATE ON precos
BEGIN
    SELECT RAISE(ABORT, 'lançamento de preço não se altera');
END;
