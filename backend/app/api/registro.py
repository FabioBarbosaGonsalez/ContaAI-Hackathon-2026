"""Registros do servidor sem dado pessoal (C3-B, etapa 7; plano v2.1, decisão 4 da exclusão da conta).

1. **Log de acesso:** o do uvicorn sai, porque grava o IP e o caminho com o CNPJ (`/empresas/12ABC34501DE35`). O
   nosso grava o método, a rota-modelo (`/empresas/{cnpj}`), o status e a duração. Um caminho que não é rota sai
   como "-", porque pode trazer qualquer coisa.
2. **Erro não tratado:** a mensagem da exceção pode repetir um valor enviado (um e-mail, um CNPJ, um trecho da
   nota). O log leva só o tipo da exceção e onde ela aconteceu (arquivo, linha e função), sem a mensagem. O
   Starlette relança a exceção depois do 500 (starlette/middleware/errors.py), e o uvicorn grava "Exception in ASGI
   application" com a pilha: o mesmo filtro vale para o logger dele.
"""

from __future__ import annotations

import logging
import re
import time
import traceback
from collections.abc import Awaitable, Callable, Iterable, Iterator
from pathlib import Path

from fastapi import Request, Response
from starlette.routing import BaseRoute, compile_path

Proximo = Callable[[Request], Awaitable[Response]]

log_acesso = logging.getLogger("contaai.acesso")
_RAIZ = Path(__file__).resolve().parents[2]  # backend/
QUADROS = 6  # os quadros mais internos da pilha: onde o erro aconteceu


def _onde(caminho: str) -> str:
    """O arquivo relativo ao backend (ou só o nome, fora dele): o log não leva a pasta de quem roda o servidor."""
    try:
        return Path(caminho).resolve().relative_to(_RAIZ).as_posix()
    except ValueError:
        return Path(caminho).name


def resumo_da_excecao(exc: BaseException) -> str:
    """O tipo e os quadros da pilha (arquivo:linha em função), sem a mensagem e sem os valores das variáveis."""
    quadros = traceback.extract_tb(exc.__traceback__)[-QUADROS:]
    pilha = " <- ".join(f"{_onde(q.filename)}:{q.lineno} em {q.name}" for q in reversed(quadros))
    return f"{type(exc).__module__}.{type(exc).__qualname__}" + (f" ({pilha})" if pilha else "")


class SemMensagemDaExcecao(logging.Filter):
    """Troca a pilha completa de um registro (exc_info) pelo resumo, sem a mensagem da exceção."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[1] is not None:
            record.msg = f"{record.getMessage().strip()}: {resumo_da_excecao(record.exc_info[1])}"
            record.args = None
            record.exc_info = None
            record.exc_text = None
        return True


_FILTRO = SemMensagemDaExcecao()


def configurar() -> None:
    """Idempotente: na montagem do app e na subida. O uvicorn configura os loggers dele antes de importar o app
    (uvicorn.Config.configure_logging), então o que muda aqui vale para o processo inteiro."""
    acesso_uvicorn = logging.getLogger("uvicorn.access")
    acesso_uvicorn.disabled = True  # o mesmo que --no-access-log, sem depender de como o servidor é chamado
    erro_uvicorn = logging.getLogger("uvicorn.error")
    if _FILTRO not in erro_uvicorn.filters:
        erro_uvicorn.addFilter(_FILTRO)
    nosso = logging.getLogger("contaai")
    if _FILTRO not in nosso.filters:
        nosso.addFilter(_FILTRO)
    if not nosso.handlers:
        # Sem handler, o logging só mostra WARNING ou mais (logging.lastResort): o log de acesso é INFO. O registro
        # continua subindo para a raiz (os testes leem por ela), que o uvicorn não configura.
        saida = logging.StreamHandler()
        saida.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        saida.addFilter(_FILTRO)  # o filtro do logger não vale para os filhos (contaai.agente, contaai.motores)
        nosso.addHandler(saida)
        nosso.setLevel(logging.INFO)


def _modelos(rotas: Iterable[BaseRoute], prefixo: str = "") -> Iterator[tuple[re.Pattern[str], str]]:
    """Os caminhos de todas as rotas, com o prefixo de cada inclusão. No FastAPI 0.165, as rotas de um APIRouter
    incluído ficam dentro de um `_IncludedRouter` (original_router e include_context.prefix)."""
    for rota in rotas:
        original = getattr(rota, "original_router", None)
        if original is not None:
            contexto = getattr(rota, "include_context", None)
            yield from _modelos(original.routes, prefixo + str(getattr(contexto, "prefix", "") or ""))
        elif isinstance(caminho := getattr(rota, "path", None), str):
            yield compile_path(prefixo + caminho)[0], prefixo + caminho


_CACHE_MODELOS: dict[int, list[tuple[re.Pattern[str], str]]] = {}


def rota_modelo(request: Request) -> str:
    """O caminho da rota (`/empresas/{cnpj}`), nunca o caminho pedido; "-" se nenhuma rota serve.

    Depois do roteamento, o próprio FastAPI deixa a rota em scope["route"] (também no 405). Uma recusa dos
    middlewares (403, 411, 413, 429) acontece antes dele: aí o caminho é comparado com os modelos das rotas."""
    rota = request.scope.get("route")
    if isinstance(caminho := getattr(rota, "path", None), str):
        return caminho
    app = request.app
    modelos = _CACHE_MODELOS.get(id(app))
    if modelos is None:
        modelos = _CACHE_MODELOS[id(app)] = list(_modelos(app.router.routes))
    pedido = request.scope.get("path", "")
    return next((modelo for regex, modelo in modelos if regex.match(pedido)), "-")


async def registrar_acesso(request: Request, call_next: Proximo) -> Response:
    """Por fora de todos os middlewares: as recusas deles (403, 411, 413, 429) também entram."""
    inicio = time.perf_counter()
    status = 500
    try:
        resposta = await call_next(request)
        status = resposta.status_code
        return resposta
    finally:
        log_acesso.info(
            "%s %s %d %.0f ms", request.method, rota_modelo(request), status, (time.perf_counter() - inicio) * 1000
        )
