"""Índice local de NCM (E2-02): gerado dos dados abertos do motor RR e buscado por palavras."""

from __future__ import annotations

from app.classificacao.indice import buscar, carregar, palavras
from app.config import Configuracao


def test_indice_veio_do_motor_fixado() -> None:
    idx = carregar()
    assert idx.versaoApp == Configuracao().versao_rr  # P5: regerar ao trocar a versão do motor
    assert len(idx.ncms) > 10_000
    assert all(len(n.ncm) == 8 and n.ncm.isdigit() for n in idx.ncms)
    assert not any("<" in n.descricao for n in idx.ncms)  # marcação HTML dos dados abertos removida


def test_frases_da_demo_trazem_a_ncm_do_catalogo_primeiro() -> None:
    assert buscar("Arroz polido não parboilizado, pacote 5 kg")[0].ncm == "10063021"
    assert buscar("Cerveja de malte, lata 350 ml")[0].ncm == "22030000"
    assert buscar("Chocolate não recheado, barra 90 g")[0].ncm == "18063210"
    assert buscar("cerveja")[0].ncm == "22030000"


def test_cerveja_vem_marcada_com_imposto_seletivo() -> None:
    assert buscar("cerveja")[0].tributadoPeloImpostoSeletivo


def test_codigo_de_ncm_e_buscado_direto() -> None:
    assert [n.ncm for n in buscar("2203.00.00")] == ["22030000"]
    assert buscar("99999999") == []


def test_sem_palavra_util_nao_busca() -> None:
    assert buscar("de da do 5 kg") == []
    # Limite conhecido (sem sinônimos): o nome oficial da posição 22.02 não usa "refrigerante".
    assert all(n.ncm[:4] != "2202" for n in buscar("refrigerante"))


def test_limite_e_palavras() -> None:
    assert len(buscar("carne", limite=5)) == 5
    assert palavras("Cerveja de Malte, LATA 350 ml") == ["cerveja", "malte"]


def test_termo_da_nomenclatura_acha_o_que_o_nome_comum_nao_acha() -> None:
    # É o exemplo da regra 2a das instruções do agente (app/agente/prompt.py): precisa continuar valendo.
    assert buscar("águas adicionadas de açúcar")[0].ncm == "22021000"
