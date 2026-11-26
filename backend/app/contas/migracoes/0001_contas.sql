-- Contas (C1, ADR 0015). Banco próprio (contas.db), separado do banco da demonstração: o POST /demo/restaurar
-- substitui o banco da demo inteiro, e as contas reais não podem ir junto.
--
-- SQL portável para o PostgreSQL (plano v2.1, decisão 5): ids em texto, datas ISO 8601 em UTC (texto, comparadas
-- como texto: todas são gravadas com o mesmo formato), inteiros e textos simples, sem STRICT, GLOB nem julianday.
-- A organização aparece em toda tabela que guarda dado de uma organização.

CREATE TABLE organizacoes (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    criada_em TEXT NOT NULL
);

-- Pendente: cadastro feito e segundo fator ainda não confirmado. Vence em pendente_ate e pode ser refeito.
CREATE TABLE usuarios (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    situacao TEXT NOT NULL CHECK (situacao IN ('pendente', 'ativa')),
    pendente_ate TEXT,
    criado_em TEXT NOT NULL
);

CREATE TABLE membros (
    organizacao_id TEXT NOT NULL REFERENCES organizacoes (id) ON DELETE CASCADE,
    usuario_id TEXT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    papel TEXT NOT NULL CHECK (papel IN ('dono', 'membro')),
    desde TEXT NOT NULL,
    PRIMARY KEY (organizacao_id, usuario_id)
);
CREATE INDEX membros_usuario ON membros (usuario_id);

-- Empresas (CNPJ) que a organização acessa. A C3 cadastra a empresa própria aqui.
CREATE TABLE acessos_empresa (
    organizacao_id TEXT NOT NULL REFERENCES organizacoes (id) ON DELETE CASCADE,
    cnpj TEXT NOT NULL CHECK (length(cnpj) = 14),
    desde TEXT NOT NULL,
    PRIMARY KEY (organizacao_id, cnpj)
);

-- Segundo fator (TOTP, RFC 6238). ultimo_passo: o passo de tempo do último código aceito; um código só vale uma
-- vez (NIST SP 800-63B-4, 3.1.4.2).
CREATE TABLE segundo_fator (
    usuario_id TEXT PRIMARY KEY REFERENCES usuarios (id) ON DELETE CASCADE,
    segredo TEXT NOT NULL,
    ultimo_passo INTEGER NOT NULL DEFAULT 0,
    confirmado_em TEXT
);

-- Códigos de recuperação: só o SHA-256 (cada código tem 65 bits sorteados; NIST 4.2 pede o hash). Uso único.
CREATE TABLE codigos_recuperacao (
    hash TEXT PRIMARY KEY,
    usuario_id TEXT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    criado_em TEXT NOT NULL
);
CREATE INDEX codigos_usuario ON codigos_recuperacao (usuario_id);

-- Sessões e passes: só o SHA-256 do token (256 bits sorteados). O passe é a etapa entre a senha e o código
-- (tipo 'entrada') ou entre o cadastro e a confirmação do segundo fator (tipo 'ativacao').
CREATE TABLE sessoes (
    hash TEXT PRIMARY KEY,
    usuario_id TEXT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    organizacao_id TEXT NOT NULL REFERENCES organizacoes (id) ON DELETE CASCADE,
    criada_em TEXT NOT NULL,
    ultimo_uso TEXT NOT NULL,
    expira_em TEXT NOT NULL
);
CREATE INDEX sessoes_usuario ON sessoes (usuario_id);

CREATE TABLE passes (
    hash TEXT PRIMARY KEY,
    usuario_id TEXT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'ativacao')),
    expira_em TEXT NOT NULL
);
CREATE INDEX passes_usuario ON passes (usuario_id);

-- Falhas seguidas de entrada (senha, código ou código de recuperação), por conta (OWASP: o contador fica na
-- conta). espera_ate: a espera crescente a partir da 5ª falha; bloqueada: 1 depois de 100 falhas (NIST 3.2.2),
-- e só um administrador desbloqueia.
CREATE TABLE tentativas (
    usuario_id TEXT PRIMARY KEY REFERENCES usuarios (id) ON DELETE CASCADE,
    falhas_seguidas INTEGER NOT NULL DEFAULT 0,
    espera_ate TEXT,
    bloqueada INTEGER NOT NULL DEFAULT 0 CHECK (bloqueada IN (0, 1))
);

-- Eventos que a pessoa precisa ver (ex.: código de recuperação usado, NIST 4.2 pede o aviso). Sem IP e sem
-- navegador: só o tipo e a data.
CREATE TABLE eventos_seguranca (
    id TEXT PRIMARY KEY,
    usuario_id TEXT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    em TEXT NOT NULL
);
CREATE INDEX eventos_usuario ON eventos_seguranca (usuario_id, em);
