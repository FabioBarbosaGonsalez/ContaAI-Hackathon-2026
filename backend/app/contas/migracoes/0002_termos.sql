-- Aceite dos termos de uso (C2, B0; ADR 0015, revisão de 2026-11-26): a versão aceita no cadastro e quando.
--
-- As duas colunas ficam vazias para quem se cadastrou antes desta migração. Elas são apagadas junto com a pessoa
-- (a linha de usuarios), como o resto dos dados dela (LGPD, art. 18 VI).
--
-- SQL portável para o PostgreSQL (plano v2.1, decisão 5): um ADD COLUMN por comando, texto e data ISO 8601 em UTC.

ALTER TABLE usuarios ADD COLUMN termos_versao TEXT;
ALTER TABLE usuarios ADD COLUMN termos_aceitos_em TEXT;
