# ADR 0007: Comparação Simples tradicional × híbrido para uma venda B2B

- Status: aceito
- Data: 2026-11-25
- Etapa: E3 (E3-01, E3-02, E3-04 e E3-05; a E3-03 passa para a E5)
- Código: `backend/app/regime/comparar.py`, a rota `POST /regime/comparar` em `backend/app/main.py` (desde o ADR 0009, `backend/app/api/rotas/calculo.py`), a ferramenta `comparar_regimes` em `backend/app/agente/ferramentas.py`

## Contexto

A E3 do plano tem duas partes. A primeira é `POST /regime/comparar`: o lado híbrido sai do motor RR e o lado tradicional do motor SN, numa venda a um cliente do regime regular (seção 11.2). A segunda é o crédito das compras, lido do grupo IBSCBS da NF-e quando a nota traz esse grupo; senão, calculado pela API sobre o custo, com a hipótese de fornecedor no regime regular. Critério de saída: a tela de decisão mostra (1) a diferença de caixa da empresa, (2) o crédito que o cliente leva e (3) o custo líquido do cliente em cada regime, com as premissas impressas.

Até a E2 a rota servia o mock da referência (`scripts/gerar_mocks.py`) e respondia 501 no modo real.

Decisões do usuário em 2026-11-25, todas como sugeridas:

1. **Tela (E3-03) na E5.** A E3 entrega só o backend. O projeto ainda não tem frontend, e o processo da skill de design (lint, inspetor e crítica) é da E5. O critério de saída é conferido pelo contrato e pelo `/docs`: os três números e as premissas estão na resposta. A tela continua com o desenho do inventário (`.taste-skill/app/inventario.md`, "Decisão de regime").
2. **Item sem custo: 422.** Sem custo não há crédito das compras, e o lado híbrido sairia pior do que é.
3. **Detalhamento por item na resposta** (`itens[]`). Os totais são a soma das linhas mostradas, como pede o plano (seção 16, Regime).
4. **Preço de empate com um concorrente do regime regular:** fica para o fim da etapa, como opcional. Entrou, com a hipótese descrita abaixo.
5. **Biscoito no lugar do arroz na venda ao cliente B2B** (decisão do usuário, depois da verificação abaixo). O arroz continua no catálogo, porque demonstra a busca de classificação e a explicação da redução.

## Decisão

### Cálculo (mesmo preço total V ao cliente, linha a linha)

| | Simples tradicional | Simples híbrido |
|---|---|---|
| Tributo | CBS + IBS do motor SN sobre V | débito D = CBS + IBS do motor RR sobre a base B |
| Base | V | B tal que B + D(B) + IS(B) = V (ajuste afim: duas avaliações, V e 2V, mais a confirmação) |
| Crédito do cliente | igual ao tributo (LC 214/2025, art. 47, §9º, II) | igual a D |
| Custo líquido do cliente | V − crédito | preço − D |
| Crédito das compras | não aproveitado (art. 47, §9º, I) | Cc = crédito por unidade × quantidade vendida |

- `diferencaCaixa` = tributo tradicional − (D − Cc), a preço igual (ADR 0003). Os centavos que sobram do arredondamento da base aparecem à parte, em `diferencaPrecoCliente`. Na demo: R$ 0,03.
- **Tolerância da base:** R$ 0,05 por linha. Se a confirmação errar por mais que isso (motor não linear), a secante refina até 3 vezes. Se ainda não fechar, a resposta é 422.
- **Chamadas aos motores:** SN 1 (venda) + 2 (empate); RR 3 (reta e confirmação) + 1 lote para o crédito pelo motor, quando algum item não traz o crédito. São até 7 chamadas por requisição, e a rota está no limite por IP (`ROTAS_LIMITADAS`).
- **Recusas:** um item que um dos motores não calcula recusa a comparação inteira (422 `RecusaCalculo`, hoje `ProblemaCalculo` pelo ADR 0009, com os erros do motor), porque os dois lados precisam ter os mesmos itens. A validação de entrada também recusa:
  - data antes de 2027 (em 2026 o motor SN devolve VSN-015 e não há lado tradicional; isso fecha, para esta rota, o ponto aberto no ADR 0004);
  - item sem custo;
  - ids repetidos;
  - sem `premissasDas`;
  - serviço (NBS);
  - IS com incidência (CST ≠ 200).

### Crédito das compras (E3-02)

- `fonteCredito` por item:
  - `nfe`: `creditoCompraUnitario` informado. É o grupo IBSCBS da nota, que a E4 vai ler do XML.
  - `motor`: CBS + IBS do motor RR sobre o custo das unidades vendidas, na data e com as alíquotas da operação. Sai a premissa "Crédito das compras sem valor informado".
  - `custo_zero`: custo informado como zero.
- Base legal impressa: LC 214/2025, art. 47, caput. O contribuinte do regime regular apropria os créditos de IBS e CBS das aquisições "quando ocorrer a extinção […] dos débitos". O art. 49 diz que a alíquota zero não permite crédito: o arroz da cesta sai com crédito zero.
- **Leitura da equipe:** com a opção do art. 41, §3º, não vale a vedação do art. 47, §9º, I, cujo caput se aplica "quando não for exercida a opção pelo regime regular". A leitura fica rotulada como da equipe.

### Venda da demo sem item com redução (decisão 5)

- **Problema:** o arroz era mais da metade da venda (R$ 11.160,00) e tem redução de 100% no regime regular (200003, Anexo I). No Simples tradicional, o motor SN aplica a alíquota efetiva cheia a ele (R$ 131,03). Não se sabe se a alíquota zero da cesta básica vale dentro do DAS: lidos em 2026-11-25 no Planalto, a LC 123 (arts. 13 e 18) e a LC 214 (arts. 41, 125 a 128) não dizem isso expressamente. O texto mais próximo é a LC 214, art. 41, §2º ("Os contribuintes optantes pelo Simples Nacional ou pelo MEI ficam sujeitos às regras desses regimes"), que não resolve a questão. Com o arroz, a diferença de caixa era +R$ 100,50; sem a premissa, seria −R$ 30,53: o sinal da decisão dependia de um ponto não verificado.
- **Troca:** biscoito doce, NCM 19053100 ("Bolachas e biscoitos, adicionados de edulcorantes"). Verificação oficial, na base da calculadora da Receita (motor RR 1.7.2, banco V0073), em 2027-03-16:
  - nenhuma classificação com redução específica do produto (método do ADR 0003), e a NCM não é tributada pelo IS (`tributadoPeloImpostoSeletivo: false`);
  - no motor RR, 000001 calcula; 200003 ("Vendas de produtos destinados à alimentação humana (Anexo I)") e 200034 ("Fornecimento dos alimentos destinados ao consumo humano (Anexo VII)") são recusadas com REG-011; no arroz, de controle, 200003 é aceita;
  - no motor SN, 000001 calcula.
  - Também passaram na busca (sem o teste nos motores): sorvete 21050010, maionese 21039011 e molho de tomate 21032010.
  - Limite: a fonte é a tabela oficial da calculadora, não o texto dos Anexos I e VII da LC 214, que não foi lido.
- Preço (R$ 4,49) e custo (R$ 3,10) do biscoito são fictícios. Ele entrou nas duas notas de compra (grupo IBSCBS na nota 2), então o crédito vem da nota.

### Preço de empate (opcional da decisão 4)

`empateTradicional` responde: que preço, no tradicional, dá ao cliente o mesmo custo líquido que ele teria num concorrente do regime regular cobrando o mesmo preço total? Nesse concorrente, o custo líquido do cliente é o do lado híbrido.

- A conta é linha a linha: P − T_SN(P) = custo líquido híbrido da linha, por ajuste afim no motor SN, com arredondamento ao centavo para baixo e confirmação.
- Se não fechar dentro de R$ 0,05 por linha, o campo vem vazio e a comparação segue.
- A hipótese sai impressa no campo `hipotese`. Na demo: preço de empate R$ 18.489,49, ou R$ 1.409,16 a menos que a venda.

### Inconsistências corrigidas nesta etapa

1. **IS somado ao débito e ao crédito do cliente:** isso acontecia no mock da referência, contra a descrição do contrato ("débito = CBS + IBS"). Agora o IS fica em `hibrido.impostoSeletivo`: entra no preço, mas não no débito nem no crédito. Não muda nenhum número da demo, porque a cerveja na revenda (200007) dá IS zero. **Verificado depois (ver "Imposto Seletivo e crédito" abaixo):** o IS não gera crédito (LC 214, art. 410). Hoje o IS na comparação é sempre zero, porque o IS com incidência é recusado no tradicional.
2. **`creditoCompraUnitario`:** a descrição dizia "só é usada no Simples tradicional". Agora diz que, na comparação, ela é o crédito das compras do híbrido.
3. **NF-e na entrada:** o plano fala em "compras ou NF-e", mas o leitor de nota é da E4. Por enquanto o crédito entra por item. A docstring da requisição registra isso. (E4: o leitor existe, e o `GET /catalogo` traz o custo e o crédito da última nota de cada item, com a fonte. A tela da E5 monta a comparação com esses valores; a rota de comparação continua recebendo o crédito por item, [ADR 0008](0008-nfe-historico-e-alertas.md).)
4. **Janela de opção:** a premissa "Opção pelo Simples híbrido" é semestral, em setembro (para janeiro a junho) e em março (para julho a dezembro), e irretratável no semestre. A fonte é a LC 123, art. 13, §10, na redação da LC 227/2026, e o Portal do Simples, já verificados no ADR 0003. As datas exatas de cada ano não vão no texto: dependem do calendário do CGSN.
5. **Limite por IP:** `/regime/comparar` não estava em `ROTAS_LIMITADAS`, porque até a E2 só servia mock. Agora está.
6. **Premissa do arroz:** a referência dizia que o resultado depende dessa premissa. A frase voltou como simplificação ("O resultado da comparação depende dela"), sempre que um item tem tratamento diferente de 000.
7. **Arroz no ADR 0003, um centavo a mais:** o ADR dizia R$ 131,04 (e R$ 102,62 sem o arroz). O motor SN dá R$ 131,03 na linha de 400 × R$ 27,90, e R$ 102,63 sem o arroz. Ficou registrado também que, sem a premissa do arroz, a diferença de caixa passa a −R$ 30,53: o sinal inverte.
8. **Premissas diferentes entre mock e modo real:** os mocks de carrinho, preço-alvo e explicação usavam as premissas e os rótulos da referência da E0 ("Cesta básica dentro do DAS", "Imposto Seletivo da cerveja"), diferentes dos que o modo real imprime. Além disso, o mock da explicação mostrava a memória de cálculo de um lote de 100 unidades, enquanto o `GET /explicar` real calcula 1 unidade. Agora os três mocks saem do código de produção (`producao()` em `scripts/gerar_mocks.py`). O carrinho e o preço-alvo da referência ficam no gerador como conferência: se a produção divergir deles nos campos numéricos, nenhum mock é gravado (`Divergencia`). Nesta geração não houve divergência. No carrinho do híbrido, `versoes.motorSimplesNacional` passou a `null`: o modo real só informa os motores que chamou.

### Conferência

- O gerador de mocks (`scripts/gerar_mocks.py`) passou a usar o código de produção para a comparação, com a compra mensal do cliente B2B e o custo da última nota.
- O golden `tests/test_regime_golden.py` confere três coisas.
  - A rota real devolve exatamente o mock.
  - A venda da demo (biscoito, cerveja e chocolate) dá:

| Grandeza | Valor |
|---|---|
| Venda | R$ 19.898,65 |
| Tributo no DAS | R$ 233,63 |
| Débito | R$ 1.626,26 |
| Crédito das compras | R$ 1.266,84 |
| Tributo líquido | R$ 359,42 |
| Diferença de caixa | −R$ 125,79 |
| Crédito do cliente | R$ 233,63 no tradicional × R$ 1.626,26 no híbrido |

  - A cesta antiga, com arroz, bate com a implementação de referência da E0, que era independente do código de produção:

| Grandeza | Valor |
|---|---|
| Venda | R$ 19.901,00 |
| Tributo no DAS | R$ 233,66 |
| Débito | R$ 714,39 |
| Crédito das compras | R$ 581,23 |
| Tributo líquido | R$ 133,16 |
| Preço no híbrido | R$ 19.901,03 |
| Diferença de caixa | R$ 100,50 |

- CI: `tests/test_regime.py`, com motores falsos. Cobre as contas que fecham, as fontes do crédito, o número de chamadas, um motor não linear (com refino), as recusas, a validação, as falhas sem vazamento, o limite por IP e o empate ausente.

### Agente (E3-04)

- `comparar_regimes(itemIds?, clienteNome?)` compara os itens confirmados do contexto e precisa de `premissasDas`.
- O roteiro cita só números do resultado, com o sinal do JSON. Quando o híbrido deixa menos caixa, a frase sai sem número, porque o valor absoluto não está no JSON e o verificador o recusaria. A resposta sempre termina com "validar com o contador". O verificador continua recusando "opte pelo …".

## Imposto Seletivo e crédito (verificado em 2026-11-25)

Fonte: o Livro II da LC 214/2025, no texto do Planalto (lcp214.htm), copiado pelo usuário do navegador, porque a ferramenta automática não lia a página além do art. 233.

- **Art. 410:** "O Imposto Seletivo incidirá uma única vez sobre o bem ou serviço, sendo vedado qualquer tipo de aproveitamento de crédito do imposto com operações anteriores ou geração de créditos para operações posteriores." O IS não gera crédito para quem compra. A regra do código (IS no preço, fora do débito e do crédito do cliente) está certa, e a premissa impressa agora cita o artigo.
- **Art. 412, I, e art. 424, I:** o fato gerador é o "primeiro fornecimento", e o contribuinte é "o fabricante, no primeiro fornecimento", na redação da LC 227/2026. Na revenda pela distribuidora o IS não incide de novo, o que confirma a classificação 200007 da cerveja e o IS zero que o motor devolve.
- **Art. 409, §1º, IV e V:** bebidas alcoólicas e bebidas açucaradas estão no campo do IS. O biscoito não está na lista do art. 409, e os dados abertos marcam a NCM 19053100 como não tributada pelo IS.
- **Art. 417, I:** a CBS, o IBS e o próprio IS não integram a base do IS.
- **CF, art. 153, §6º** (incluído pela EC 132/2023; texto do Planalto, constituicao.htm, copiado pelo usuário): o IS "II - incidirá uma única vez sobre o bem ou serviço" e "IV - integrará a base de cálculo dos tributos previstos nos arts. 155, II, 156, III, 156-A e 195, V", ou seja, do IBS e da CBS. Nenhum inciso trata de crédito. O motor RR já aplica o inciso IV: no exemplo oficial, a CBS da cerveja com IS tributado sai sobre vBC R$ 165,00 (R$ 150,00 + IS R$ 15,00; ADR 0004). Por isso a base do híbrido é achada com o tributo que o motor devolve, e o backend não soma o IS à base por conta própria.

## Consequências

- A E3 está completa no backend. O modo real calcula a comparação; o modo mock serve a saída real da demo.
- O contrato mudou de forma aditiva: `data`, `itens[]`, `diferencaPrecoCliente`, `empateTradicional` e `hibrido.impostoSeletivo`. Ainda não há frontend consumindo, então nada quebra.
- **Resolvidos no fim da etapa:**
  - **Aviso "httpx2" do Starlette:** o Starlette 1.10.0 instalado prefere o `httpx2` no `TestClient` e cai no `httpx` com o aviso (conferido em `starlette/testclient.py`). O `httpx2` é da organização Pydantic no PyPI, com código em github.com/pydantic/httpx2, licença BSD-3-Clause e publicação verificada pelo PyPI. Entrou só como dependência de teste (`[project.optional-dependencies].dev`), com as dependências `httpcore2` (mesmo repositório, BSD-3-Clause) e `truststore` (MIT). Os testes passam com `-W error::DeprecationWarning`. O código da aplicação segue no `httpx`.
  - **Tradicional antes de 2027:** carrinho, preço-alvo e explicação recusam com 422 e mensagem clara antes de chamar o motor (`validar_data_do_tradicional`). O motivo (VSN-015 no motor SN) segue conferido no golden. O contexto do chat não é recusado, para a busca de NCM continuar funcionando; as ferramentas de cálculo devolvem a mensagem como erro.
  - **Imports entre testes:** o verificador comum foi para `tests/apoio_regime.py`, e o pytest declara `pythonpath = ["."]`, sem depender da instalação editável. O ruff passou a tratar `tests` como código do projeto.
- **Continuam abertos:**
  - a premissa do arroz no DAS (contador, E0-08): saiu da comparação da demo, mas continua no carrinho e na explicação do arroz no tradicional;
  - IS com incidência no tradicional (422).
