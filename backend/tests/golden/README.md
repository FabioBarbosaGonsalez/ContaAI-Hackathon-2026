# Respostas de referência (golden)

| Arquivo | O que é |
|---|---|
| `rr-operacao-exemplo-oficial.json` | Entrada do exemplo oficial de `docs/exemplos.md` da calculadora-rtc-regime-regular (tag 1.7.2, licença MIT): arroz, cerveja com IS, educação e o item com REG-011. CBS 8,8% e IBS 0,05% são **entradas do exemplo**, não alíquotas oficiais. |
| `rr-exemplo-oficial.resposta.json` | Resposta do motor RR 1.7.2 (banco V0073) a essa entrada. |
| `sn-operacao-nao-assistido-anexo-i.json` | Entrada nossa para o motor SN 1.0.2 (modo não assistido, anexo I, atividade 01). `pCBSSN 1.1612` e `pIBSSN 0.0129` são os **valores de exemplo do esquema OpenAPI do motor**, não alíquotas de nenhum contribuinte. Ver `docs/adr/0001-lado-tradicional-do-simples.md`. |
| `sn-nao-assistido-anexo-i.resposta.json` | Resposta do motor SN 1.0.2 a essa entrada. |

Regravar só ao trocar a versão fixada de um motor, em PR próprio: `make gravar-golden` (ou `cd backend && uv run python scripts/gravar_golden.py`) com os motores de pé, e revisar a diferença.
