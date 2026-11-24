"""Candidatos de classificação (NCM + cClassTrib) para o usuário confirmar (P3, E2-02).

Mesmo método do mock da E0 (ADR 0003): as classificações válidas para a NCM, segundo o próprio
motor (ncm-aplicavel), menos as que também valem para uma NCM sem benefício (NCM_NEUTRA), mais a
000001 (tributação integral) quando válida. O que sobra é o que é específico do produto. A escolha
continua do usuário ou do contador.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.classificacao import indice
from app.contrato import BuscaNcmResposta, CandidatoNcm, ClassificacaoCandidata
from app.motores.dados_abertos import NCM_NEUTRA, DadosAbertos

C2 = Decimal("0.01")
INTEGRAL = "000001"
AVISO_CANDIDATOS = (
    "Candidatos para o usuário confirmar. A classificação fiscal é decisão do usuário ou do contador (P3)."
)


async def classificacoes_da_ncm(da: DadosAbertos, ncm: str, data: date) -> list[ClassificacaoCandidata]:
    validas = await da.validas_para_ncm(ncm, data)
    neutras = await da.validas_para_ncm(NCM_NEUTRA, data)
    # Todas as válidas, sem cortar (cortar seria julgar qual está certa, P3): as específicas do produto
    # primeiro e a tributação integral por último (ADR 0006).
    codigos = sorted(validas - neutras) + sorted({INTEGRAL} & validas)
    catalogo = {c.codigo: c for c in await da.classificacoes(data)}
    fund = {f.codigoClassificacaoTributaria: f for f in await da.fundamentacoes(data)}
    saida = []
    for c in codigos:
        f = fund.get(c)
        if f is None or c not in catalogo:
            continue  # sem CST na fundamentação não há como enviar ao motor; não inventamos
        saida.append(
            ClassificacaoCandidata(
                cClassTrib=c,
                cst=f.codigoSituacaoTributaria,
                descricao=catalogo[c].descricao,
                reducaoPct=Decimal(str(catalogo[c].percentualReducaoCbs or 0)).quantize(C2),
                especificaDoProduto=c not in neutras,
                fundamentacao=f.textoCurto,
            )
        )
    return saida


async def candidato(da: DadosAbertos, ncm: str, data: date) -> CandidatoNcm | None:
    """A NCM com a hierarquia oficial do motor na data (None se não estiver vigente) e as classificações."""
    info = await da.ncm(ncm, data)
    if info is None:
        return None
    return CandidatoNcm(
        ncm=ncm,
        descricao=info.hierarquia(),
        tributadoPeloImpostoSeletivo=info.tributadoPeloImpostoSeletivo,
        classificacoes=await classificacoes_da_ncm(da, ncm, data),
    )


async def buscar_candidatos(da: DadosAbertos, texto: str, data: date, limite: int = 3) -> BuscaNcmResposta:
    idx = indice.carregar()
    candidatos = []
    for achada in indice.buscar(texto, limite=limite, indice=idx):
        c = await candidato(da, achada.ncm, data)
        if c is not None:
            candidatos.append(c)
    return BuscaNcmResposta(
        consulta=texto,
        candidatos=candidatos,
        aviso=AVISO_CANDIDATOS,
        fonte=f"Índice local de NCM ({idx.fonte}); classificações validadas no motor RR na data {data.isoformat()}.",
    )
