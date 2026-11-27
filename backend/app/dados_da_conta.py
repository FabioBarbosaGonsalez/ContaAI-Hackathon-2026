"""O arquivo dos dados da conta (C3-B, etapa 7; LGPD, arts. 18 II e V e 19).

O art. 19 pede o acesso "em formato simplificado, imediatamente" (inciso I) e, quando o tratamento vem de contrato,
a "cópia eletrônica integral" num "formato que permita a sua utilização subsequente" (§3º). O arquivo é um JSON
montado na hora, com o que o ContaAI guarda: a pessoa (contas.db) e, de cada organização dela, as empresas (o banco
da organização).

Fica de fora o que serve só para conferir a identidade (a senha, o segredo do segundo fator e os hashes de senha,
token e código) e os dados dos outros integrantes da organização. `NAO_INCLUIDO` diz isso no próprio arquivo.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.contas.servico import Contas
from app.contrato import (
    ContaDadosResposta,
    DadosDaPessoa,
    EmpresaExportada,
    EventoSeguranca,
    OrganizacaoExportada,
    SessaoExportada,
    TentativasExportadas,
    TermosDaConta,
)
from app.persistencia.banco import Banco
from app.persistencia.repositorio import Repositorio

FORMATO = "contaai-dados-1"
NAO_INCLUIDO = [
    "A senha: o ContaAI guarda só o hash dela, e nenhum hash vai no arquivo.",
    "O segredo do segundo fator: ele fica no servidor só para conferir os códigos do aplicativo.",
    "Os códigos de recuperação e os tokens de sessão: o ContaAI guarda só o hash de cada um (o arquivo diz quantos "
    "códigos restam).",
    "Os passes da entrada e do cadastro, que valem por 5 minutos.",
    "O XML das notas: o ContaAI não guarda o arquivo, só o sha256 dele e o recibo da importação.",
    "Os outros integrantes da organização.",
]
AVISO = (
    "Guarde suas notas: o ContaAI não é o seu arquivo fiscal. Este arquivo tem os seus dados e os das suas "
    "empresas; guarde-o num lugar seguro."
)


def nome_do_arquivo(agora: datetime) -> str:
    return f"contaai-dados-{agora.date().isoformat()}.json"


def montar(
    contas: Contas, banco_da_organizacao: Callable[[str], Banco], usuario_id: str, token: str, agora: datetime
) -> ContaDadosResposta:
    """Uma leitura do contas.db e uma de cada banco de organização. O banco só é aberto se a organização tem
    empresa: abrir cria o arquivo, e uma organização sem empresa não tem nada nele."""
    pessoa = contas.dados_da_pessoa(usuario_id, token)
    organizacoes = []
    for org in pessoa.organizacoes:
        empresas = []
        if org.acessos:
            repo = Repositorio(banco_da_organizacao(org.id))
            with repo.leitura() as s:
                for cnpj, desde in org.acessos:
                    empresas.append(
                        EmpresaExportada.model_validate(
                            {"cnpj": cnpj, "acessoDesde": desde, **s.exportar_empresa(cnpj)}
                        )
                    )
        organizacoes.append(
            OrganizacaoExportada(
                id=org.id, nome=org.nome, criadaEm=org.criada_em, papel=org.papel, desde=org.desde, empresas=empresas
            )
        )
    tentativas = None
    if pessoa.tentativas is not None:
        falhas, espera, bloqueada = pessoa.tentativas
        tentativas = TentativasExportadas(falhasSeguidas=falhas, esperaAte=espera, bloqueada=bloqueada)
    return ContaDadosResposta(
        formato=FORMATO,
        geradoEm=agora,
        conta=DadosDaPessoa(
            email=pessoa.email,
            criadaEm=pessoa.criada_em,
            situacao=pessoa.situacao,
            termos=TermosDaConta(versao=pessoa.termos[0], aceitosEm=pessoa.termos[1]) if pessoa.termos else None,
            segundoFatorConfirmadoEm=pessoa.segundo_fator_confirmado_em,
            codigosRecuperacaoRestantes=pessoa.codigos_restantes,
            tentativas=tentativas,
            eventos=[EventoSeguranca(tipo=t, em=em) for t, em in pessoa.eventos],
            sessoes=[
                SessaoExportada(criadaEm=c, ultimoUso=u, expiraEm=e, atual=atual) for c, u, e, atual in pessoa.sessoes
            ],
        ),
        organizacoes=organizacoes,
        naoIncluido=NAO_INCLUIDO,
        aviso=AVISO,
    )
