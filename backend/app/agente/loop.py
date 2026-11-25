"""Loop de tool use do agente (E2-01), igual para qualquer provedor.

1. Manda ao provedor as instruções, a conversa e as ferramentas.
2. Executa as chamadas pedidas (validadas e limitadas) e devolve os resultados.
3. Repete até vir texto sem chamadas, ou até o limite de rodadas (a última vai sem ferramentas).
4. Verifica o texto (verificador.py). Se citar número sem fonte, pede uma reescrita uma vez; se
   falhar de novo, troca por uma resposta segura.
5. Monta as ações para o usuário confirmar a partir dos RESULTADOS das ferramentas, nunca do texto.

Registra em log cada chamada (nome, duração, ok) e o total por mensagem, sem o conteúdo da conversa.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agente import ferramentas
from app.agente.ferramentas import Ambiente
from app.agente.prompt import instrucoes
from app.agente.provedor import ProvedorFalhou, ProvedorLLM
from app.agente.tipos import PREFIXO_VERIFICACAO, ChamadaFerramenta, Mensagem, Pedido, ResultadoFerramenta
from app.agente.verificador import verificar
from app.classificacao.candidatos import classificacoes_da_ncm
from app.config import Configuracao
from app.contrato import (
    AVISO_LEGAL,
    AcaoAplicarPreco,
    AcaoConfirmarClassificacao,
    AcaoCorrigirClassificacao,
    AcaoProposta,
    BuscaNcmResposta,
    ChatRequisicao,
    ChatResposta,
    ClassificacaoCandidata,
    ErroMotor,
    Premissa,
)
from app.motores.cliente import FalhaMotor

log = logging.getLogger("contaai.agente")

ERROS_DE_CLASSIFICACAO = {"REG-011", "VSN-047"}
MAX_CANDIDATAS = 3
RESPOSTA_SEGURA = (
    "Não consegui escrever uma resposta com todos os números conferidos nas calculadoras oficiais. "
    "Os resultados estão nos cartões e na tabela da tela."
)
RESPOSTA_LIMITE = "O pedido precisou de mais consultas do que o limite por mensagem. Tente dividir a pergunta."
PEDIDO_REESCRITA = (
    PREFIXO_VERIFICACAO + " A resposta anterior foi recusada: {motivo}. Reescreva usando só "
    "valores que aparecem nos resultados das ferramentas, sem recomendar regime."
)


@dataclass
class Rastro:
    """Tudo que as ferramentas devolveram nesta mensagem (fontes do verificador e das ações)."""

    chamadas: list[tuple[ChamadaFerramenta, ResultadoFerramenta]] = field(default_factory=list)

    @property
    def nomes(self) -> list[str]:
        return [c.nome for c, _ in self.chamadas]

    def fontes(self) -> list[Any]:
        saida: list[Any] = []
        for chamada, resultado in self.chamadas:
            saida.append(resultado.conteudo)
            if resultado.erro:
                saida.append(chamada.argumentos)
        return saida


async def _executar(chamada: ChamadaFerramenta, amb: Ambiente) -> ResultadoFerramenta:
    inicio = time.perf_counter()
    conteudo, erro = await ferramentas.executar(chamada.nome, chamada.argumentos, amb)
    log.info("ferramenta %s ok=%s %.0f ms", chamada.nome, not erro, (time.perf_counter() - inicio) * 1000)
    return ResultadoFerramenta(id=chamada.id, nome=chamada.nome, conteudo=conteudo, erro=erro)


async def _conversar(
    provedor: ProvedorLLM, cfg: Configuracao, sistema: str, mensagens: list[Mensagem], amb: Ambiente, rastro: Rastro
) -> str:
    definicoes = ferramentas.definicoes()
    for rodada in range(cfg.llm_max_rodadas):
        ultima = rodada == cfg.llm_max_rodadas - 1 or len(rastro.chamadas) >= cfg.llm_max_chamadas
        resposta = await provedor.responder(
            Pedido(
                sistema=sistema,
                mensagens=mensagens,
                ferramentas=[] if ultima else definicoes,
                max_tokens=cfg.llm_max_tokens,
            )
        )
        if not resposta.chamadas:
            return resposta.texto.strip()
        if ultima:
            return RESPOSTA_LIMITE  # o provedor ignorou a ausência de ferramentas
        chamadas = resposta.chamadas[: cfg.llm_max_chamadas - len(rastro.chamadas)]
        resultados = [await _executar(c, amb) for c in chamadas]
        rastro.chamadas += list(zip(chamadas, resultados, strict=True))
        mensagens += [
            Mensagem(papel="assistente", texto=resposta.texto, chamadas=tuple(chamadas)),
            Mensagem(papel="ferramenta", resultados=tuple(resultados)),
        ]
    return RESPOSTA_LIMITE


async def _candidatas_para(amb: Ambiente, ncm: str, atual: str) -> list[ClassificacaoCandidata]:
    try:
        todas = await classificacoes_da_ncm(amb.dados_abertos, ncm, amb.data)
    except FalhaMotor:
        return []
    outras = [c for c in todas if c.cClassTrib != atual]
    # Primeiro as específicas do produto, depois a tributação integral.
    outras.sort(key=lambda c: (not c.especificaDoProduto, c.cClassTrib))
    return outras[:MAX_CANDIDATAS]


async def _acoes(rastro: Rastro, amb: Ambiente) -> list[AcaoProposta]:
    acoes: list[AcaoProposta] = []
    vistos: set[tuple[str, str]] = set()
    ctx = amb.contexto
    for chamada, resultado in rastro.chamadas:
        if resultado.erro:
            continue
        c = resultado.conteudo
        if chamada.nome == "buscar_ncm":
            busca = BuscaNcmResposta.model_validate(c)
            if busca.candidatos and ("buscar", busca.consulta) not in vistos:
                vistos.add(("buscar", busca.consulta))
                acoes.append(
                    AcaoConfirmarClassificacao(
                        tipo="confirmar_classificacao", itemDescricao=busca.consulta, candidatos=busca.candidatos
                    )
                )
        elif chamada.nome == "calcular_carrinho" and ctx is not None:
            for item in c.get("itens", []):
                erro = next((e for e in item.get("erros", []) if e.get("codigo") in ERROS_DE_CLASSIFICACAO), None)
                original = next((i for i in ctx.itens if i.id == item.get("id")), None)
                if erro is None or original is None or original.ncm is None or ("corrigir", original.id) in vistos:
                    continue
                vistos.add(("corrigir", original.id))
                candidatas = await _candidatas_para(amb, original.ncm, original.cClassTrib)
                if candidatas:
                    acoes.append(
                        AcaoCorrigirClassificacao(
                            tipo="corrigir_classificacao",
                            itemId=original.id,
                            erro=ErroMotor.model_validate(erro),
                            ncm=original.ncm,
                            candidatas=candidatas,
                        )
                    )
        elif chamada.nome == "preco_alvo" and ctx is not None:
            item_id = c["itemId"]
            if ("preco", item_id) in vistos:
                continue
            vistos.add(("preco", item_id))
            original = next((i for i in ctx.itens if i.id == item_id), None)
            acoes.append(
                AcaoAplicarPreco(
                    tipo="aplicar_preco",
                    itemId=item_id,
                    valorUnitarioAtual=original.valorUnitario if original else None,
                    valorUnitarioSugerido=c["valorUnitario"],
                    precoCliente=c["precoCliente"],
                    margemAlvoPct=c["margemAlvoPct"],
                    margemObtidaPct=c["margemObtidaPct"],
                )
            )
    return acoes


def _simulacao(rastro: Rastro) -> tuple[bool, str | None, list[Premissa]]:
    simulado, aviso, premissas, vistas = False, None, [], set()
    for _, resultado in rastro.chamadas:
        c = resultado.conteudo
        if resultado.erro or not isinstance(c, dict):
            continue
        if c.get("simulado"):
            simulado = True
            aviso = aviso or c.get("avisoSimulacao")
        for p in c.get("premissas", []):
            chave = (p.get("nome"), p.get("valor"))
            if chave not in vistas:
                vistas.add(chave)
                premissas.append(Premissa.model_validate(p))
    return simulado, aviso, premissas


async def responder_chat(req: ChatRequisicao, provedor: ProvedorLLM, cfg: Configuracao, amb: Ambiente) -> ChatResposta:
    inicio = time.perf_counter()
    sistema = instrucoes(req.contexto)
    mensagens = [Mensagem(papel=m.papel, texto=m.texto) for m in req.mensagens]
    rastro = Rastro()
    verificacao_final: Literal["aprovada", "resposta_segura"] = "aprovada"
    try:
        async with asyncio.timeout(cfg.llm_tempo_total_s):
            texto = await _conversar(provedor, cfg, sistema, mensagens, amb, rastro)
            v = verificar(texto, rastro.fontes())
            if not v.aprovada:
                log.warning(
                    "resposta recusada pelo verificador (%d sem fonte, %d proibidas)",
                    len(v.sem_fonte),
                    len(v.proibidas),
                )
                mensagens += [
                    Mensagem(papel="assistente", texto=texto),
                    Mensagem(papel="usuario", texto=PEDIDO_REESCRITA.format(motivo=v.motivo())),
                ]
                texto = await _conversar(provedor, cfg, sistema, mensagens, amb, rastro)
                if not verificar(texto, rastro.fontes()).aprovada:
                    texto, verificacao_final = RESPOSTA_SEGURA, "resposta_segura"
    except TimeoutError:
        raise ProvedorFalhou("A resposta demorou mais que o limite. Tente de novo.") from None

    simulado, aviso_sim, premissas = _simulacao(rastro)
    resposta = ChatResposta(
        resposta=texto or RESPOSTA_SEGURA,
        acoesPropostas=await _acoes(rastro, amb),
        ferramentasChamadas=rastro.nomes,
        provedor=provedor.nome,
        verificacao=verificacao_final,
        simulado=simulado,
        avisoSimulacao=aviso_sim,
        premissas=premissas,
        aviso=AVISO_LEGAL,
    )
    log.info(
        "chat provedor=%s ferramentas=%d verificacao=%s %.0f ms",
        provedor.nome,
        len(rastro.chamadas),
        verificacao_final,
        (time.perf_counter() - inicio) * 1000,
    )
    return resposta
