-- 0002: o que a tela da E5 grava e lê (ADR 0011).
--
-- 1. Preço lançado pela tela (ação "aplicar preço" do chat ou da tela de preço-alvo): nova origem 'tela'.
--    O SQLite não altera um CHECK: a tabela de preços é refeita com o mesmo conteúdo, o mesmo índice e o
--    mesmo gatilho de imutabilidade. Nenhuma outra tabela aponta para `precos`.
--    Regra nova: só o preço de origem 'alerta' tem alerta_id (as sementes e a tela não têm).
-- 2. Classificação corrigida pela tela (REG-011 ou VSN-047, com a confirmação do usuário, P3): um
--    lançamento por correção, só de acréscimo. A classificação atual do item é a do último lançamento;
--    sem lançamento, vale a do cadastro (itens.item_json).
-- 3. Clientes B2B de cada empresa, com a compra mensal (a venda que a tela de decisão de regime compara).
--    Vêm das sementes (data/demo/sementes.json).

CREATE TABLE precos_0002 (
    id              INTEGER PRIMARY KEY,
    cnpj            TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    valor_unitario  TEXT NOT NULL,  -- vUnCom de venda
    vigente_desde   TEXT NOT NULL CHECK (julianday(vigente_desde) IS NOT NULL),  -- UTC
    origem          TEXT NOT NULL CHECK (origem IN ('semente', 'alerta', 'tela')),
    alerta_id       TEXT REFERENCES alertas (id) ON DELETE CASCADE,
    CHECK ((origem = 'alerta') = (alerta_id IS NOT NULL)),
    FOREIGN KEY (cnpj, item_id) REFERENCES itens (cnpj, item_id) ON DELETE CASCADE
) STRICT;

INSERT INTO precos_0002 (id, cnpj, item_id, valor_unitario, vigente_desde, origem, alerta_id)
    SELECT id, cnpj, item_id, valor_unitario, vigente_desde, origem, alerta_id FROM precos;

DROP TABLE precos;

ALTER TABLE precos_0002 RENAME TO precos;

CREATE INDEX precos_por_item ON precos (cnpj, item_id, vigente_desde, id);

CREATE TRIGGER precos_sem_alteracao BEFORE UPDATE ON precos
BEGIN
    SELECT RAISE(ABORT, 'lançamento de preço não se altera');
END;

CREATE TABLE classificacoes (
    id             INTEGER PRIMARY KEY,
    cnpj           TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    cst            TEXT NOT NULL CHECK (length(cst) = 3 AND cst NOT GLOB '*[^0-9]*'),
    cclasstrib     TEXT NOT NULL CHECK (length(cclasstrib) = 6 AND cclasstrib NOT GLOB '*[^0-9]*'),
    fonte          TEXT NOT NULL,  -- montada pelo backend com os dados abertos do motor, nunca texto do usuário
    vigente_desde  TEXT NOT NULL CHECK (julianday(vigente_desde) IS NOT NULL),  -- UTC
    origem         TEXT NOT NULL CHECK (origem IN ('tela')),
    FOREIGN KEY (cnpj, item_id) REFERENCES itens (cnpj, item_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX classificacoes_por_item ON classificacoes (cnpj, item_id, id);

CREATE TRIGGER classificacoes_sem_alteracao BEFORE UPDATE ON classificacoes
BEGIN
    SELECT RAISE(ABORT, 'lançamento de classificação não se altera');
END;

CREATE TABLE clientes_b2b (
    cnpj          TEXT NOT NULL REFERENCES empresas (cnpj) ON DELETE CASCADE,  -- a empresa que vende
    cnpj_cliente  TEXT NOT NULL CHECK (length(cnpj_cliente) = 14 AND cnpj_cliente NOT GLOB '*[^0-9]*'),
    cliente_json  TEXT NOT NULL,  -- app.dados_demo.ClienteB2B, validado na leitura
    PRIMARY KEY (cnpj, cnpj_cliente)
) STRICT;
