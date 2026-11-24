# Dados de demonstração (E0-06)

Tudo aqui é **fictício** (princípio P10). Empresas, CNPJs, preços, custos, margens e quantidades não representam empresas nem preços reais. Os CNPJs têm **dígito verificador propositalmente inválido**, então não podem coincidir com o de nenhuma empresa (um teste confere isso).

| Arquivo | O que é |
|---|---|
| `distribuidora.json` | Distribuidora Serra Azul ME (fictícia): Simples, anexo I, atividade 01 (revenda), em Porto Alegre (código IBGE 4314902). Traz as premissas do cenário de março de 2027 e o catálogo de 4 itens. |
| `cliente-b2b.json` | Mercado Bom Preço Ltda (fictício), regime regular: cesta mensal de R$ 19.901,00 aos preços do catálogo (o plano fala em R$ 20 mil por mês). |
| `notas/nfe-compra-1.xml` | Compra de 02/03/2027 do Atacado Exemplo Ltda (fictício). **Sem** grupo IBSCBS: o crédito das compras sai do motor RR sobre o custo. |
| `notas/nfe-compra-2.xml` | Compra de 16/03/2027 do mesmo fornecedor: a cerveja sobe de R$ 2,60 para R$ 3,05. **Com** grupos IS e IBSCBS gerados pelo motor RR e validados no XSD oficial. |

## Catálogo

| Item | NCM | cClassTrib | Papel na demo |
|---|---|---|---|
| Arroz polido, pacote 5 kg | 10063021 | 200003 (Anexo I, redução de 100%) | Item com redução |
| Cerveja de malte, lata 350 ml | 22030000 | 000001 + IS 200007 | Alerta de margem pela nota 2 |
| Chocolate não recheado, barra 90 g | 18063210 | 000001 | Referência de alíquota cheia |
| Carne bovina desossada, resfriada (kg) | 02013000 | 200035 (errada de propósito) | Autocorreção do REG-011 |

As classificações e descrições de NCM vêm dos dados abertos do motor RR 1.7.2 e do exemplo oficial (`docs/exemplos.md`). A fonte de cada uma está no próprio JSON.

- **Item comum:** o chocolate foi escolhido porque, nos dados abertos, não tem nenhuma classificação com redução específica do produto (ADR 0003).
- **Cerveja:** usa o IS `200007` (revenda), porque o IS incide uma única vez sobre o bem, conforme a CF, art. 153, §6º, II.

## Premissas (rotuladas, nunca alíquota oficial)

- **CBS 8,8%, IBS estadual 0,05% e IBS municipal 0,05%:** entradas do exemplo oficial. Não são alíquotas oficiais (P6).
- **IS ad valorem 10%:** entrada do exemplo oficial. O motor exige essa alíquota para a NCM da cerveja mesmo na revenda, em que o IS sai zero.
- **pCBSSN 1,1612% e pIBSSN 0,0129%:** valores de exemplo do esquema OpenAPI do motor SN. Não são alíquotas de nenhum contribuinte (P8).
- **Carga atual (%):** vazia de propósito, porque é o usuário quem informa.

## Simplificações

- **As notas não são documentos fiscais válidos.** Não têm assinatura digital nem todos os campos obrigatórios, são de ambiente de homologação (`tpAmb 2`) e trazem "SEM VALOR FISCAL" em `infCpl`. Os elementos incluídos seguem a ordem do leiaute oficial da NF-e 4.00.
- **ICMS fora das contas.** Em 2027 ele ainda existe e é deduzido da base do IBS/CBS (`docs/exemplos.md` da calculadora RR).

## Como regerar

Com os motores de pé (`docker compose up -d`):

```bash
cd backend
uv run python scripts/gerar_notas_demo.py   # notas (só ao mudar o catálogo ou as premissas)
uv run python scripts/gerar_mocks.py        # mocks da API, a partir destes dados
```
