"""Exporta o contrato OpenAPI da API para docs/contrato/openapi.json (E0-05).

É o arquivo que frontend e agente leem. O teste test_openapi_exportado_esta_atualizado falha
quando o contrato muda sem reexportar, para que toda mudança de contrato seja deliberada.

Uso: cd backend && uv run python scripts/exportar_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
from app.main import app  # noqa: E402

DESTINO = RAIZ / "docs" / "contrato" / "openapi.json"


def gerar() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(gerar(), encoding="utf-8")
    print(f"Contrato exportado em {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
