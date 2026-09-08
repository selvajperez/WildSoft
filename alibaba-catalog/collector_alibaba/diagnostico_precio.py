"""
Herramienta de diagnóstico: busca un producto por texto en el HTML crudo
archivado (`paginas_html_crudo/`, generado por `collector_browser.py`) y
muestra su registro completo tal cual viene en el JSON de Alibaba, sin
pasar por `parser.py`. Sirve para ver los campos originales (`priceFrom`,
`fobPriceWithoutUnit`, etc.) de un producto puntual sin volver a navegar
Alibaba.

Uso:
    python diagnostico_precio.py "Bathroom Mat"
    python diagnostico_precio.py "Bathroom Mat" --pagina 7   # si ya se sabe la página
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))

from parser import MODULE_PRODUCT_LIST  # noqa: E402

DIR_HTML_CRUDO = Path(__file__).parent.parent / "paginas_html_crudo"


def _productos_crudos_de_pagina(html: str) -> list[dict]:
    """Como `parser._extraer_module_data`, pero devuelve los items sin normalizar."""
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find(attrs={"module-name": MODULE_PRODUCT_LIST})
    if div is None or not div.get("module-data"):
        return []
    data = json.loads(urllib.parse.unquote(div["module-data"]))
    return data.get("mds", {}).get("moduleData", {}).get("data", {}).get("productList", [])


def buscar_producto(texto: str, pagina: int | None = None) -> list[tuple[int, dict]]:
    """Devuelve [(numero_pagina, item_crudo), ...] para productos cuyo `subject` contiene `texto`."""
    patron = f"productlist-{pagina}.html" if pagina else "productlist-*.html"
    resultados = []
    texto_lower = texto.lower()

    for archivo in sorted(DIR_HTML_CRUDO.glob(patron)):
        numero_pagina = int(archivo.stem.split("-")[1])
        html = archivo.read_text(encoding="utf-8")
        for item in _productos_crudos_de_pagina(html):
            if texto_lower in (item.get("subject") or "").lower():
                resultados.append((numero_pagina, item))

    return resultados


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Busca un producto en el HTML crudo archivado y muestra su JSON completo (sin normalizar)."
    )
    argparser.add_argument("texto", help="Texto a buscar en el nombre del producto (case-insensitive).")
    argparser.add_argument("--pagina", type=int, default=None, help="Limitar la búsqueda a una página puntual.")
    args = argparser.parse_args()

    if not DIR_HTML_CRUDO.exists():
        print(f"No existe {DIR_HTML_CRUDO}. Corré collector_browser.py primero (ver README).")
        sys.exit(1)

    resultados = buscar_producto(args.texto, args.pagina)
    if not resultados:
        print(f"No se encontró ningún producto con '{args.texto}' en el HTML archivado.")
        sys.exit(1)

    for numero_pagina, item in resultados:
        print(f"--- página {numero_pagina} ---")
        print(json.dumps(item, indent=2, ensure_ascii=False))
        print()


if __name__ == "__main__":
    main()
