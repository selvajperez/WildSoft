"""
Captura automática (Chrome real, mismo perfil que `collector_browser.py`)
del listado de resultados de una búsqueda de Alibaba por palabra clave.

Fase 2 del motor de sourcing necesita, para cada candidato con demanda
confirmada en Mercado Libre, buscar productos comparables en Alibaba --
pero hasta ahora `collector.py`/`parser.py` solo saben recorrer el
catálogo COMPLETO de un proveedor puntual ya conocido (paginación fija),
no buscar por texto libre. Esta herramienta es el primer paso -- conseguir
evidencia real -- antes de escribir el parser de ese listado: nunca se
adivina la estructura del HTML sin inspeccionarlo primero (misma regla
del proyecto usada en toda la Fase 1).

La URL de búsqueda pública de Alibaba
(`https://www.alibaba.com/trade/search?SearchText=<query>`) es un punto
de partida razonable -- mismo criterio que ya funcionó con
`listado.mercadolibre.com.ar/<query>` para Mercado Libre --, pero se
confirma (o se corrige) con la propia captura real; no se asume nada
sobre el HTML resultante de antemano.

Reutiliza `navegador_ml.py` (mismo Chrome real + perfil persistente que
el resto del proyecto -- un solo login sirve para Alibaba y Mercado
Libre) y `scraper.contiene_marcadores_bloqueo` (detección de bloqueo de
Alibaba, ya confirmada con HTML real desde la Fase 0). Guarda el HTML y
un renglón en el mismo manifiesto que ya usa `capturador_exploratorio.py`
(`capturas_exploratorias/manifiesto.jsonl`), para tener todas las
capturas exploratorias del proyecto en un solo lugar.

Uso:
    python capturador_busqueda_alibaba.py "wireless earbuds"
    python capturador_busqueda_alibaba.py "cleaning brush" --login
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from capturador_exploratorio import _guardar_html, _registrar_captura  # noqa: E402
from navegador_ml import (  # noqa: E402
    confirmar_login_manual,
    contenido_seguro,
    es_primera_vez,
    navegador_persistente,
    pausar_por_bloqueo_y_continuar,
)
from scraper import contiene_marcadores_bloqueo as bloqueado_alibaba  # noqa: E402

URL_ALIBABA_HOME = "https://www.alibaba.com"
URL_BUSQUEDA_ALIBABA = "https://www.alibaba.com/trade/search?SearchText={query}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "capturador_busqueda_alibaba.log")],
)
logger = logging.getLogger("capturador_busqueda_alibaba")


def _url_busqueda(query: str) -> str:
    return URL_BUSQUEDA_ALIBABA.format(query=urllib.parse.quote(query))


def capturar_busqueda_alibaba(query: str, forzar_login: bool = False) -> Path:
    primera_vez = es_primera_vez()

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_ALIBABA_HOME, wait_until="domcontentloaded")
            confirmar_login_manual()

        url = _url_busqueda(query)
        etiqueta = f"búsqueda Alibaba '{query}'"
        logger.info("Abriendo %s: %s", etiqueta, url)

        pagina.goto(url, wait_until="domcontentloaded")
        html = contenido_seguro(pagina)

        if bloqueado_alibaba(html):
            html = pausar_por_bloqueo_y_continuar(pagina, url, etiqueta, sigue_bloqueado=bloqueado_alibaba, sitio="Alibaba")

        archivo = _guardar_html("alibaba_busqueda", html)
        _registrar_captura("alibaba_busqueda", url, archivo, bloqueado_alibaba(html))
        logger.info("%s guardada en %s", etiqueta, archivo)

    return archivo


def main() -> None:
    argparser = argparse.ArgumentParser(description="Captura automática de un listado de búsqueda de Alibaba.")
    argparser.add_argument("query", help="Palabra clave a buscar en Alibaba (ej. el nombre de un candidato de ML).")
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    args = argparser.parse_args()

    archivo = capturar_busqueda_alibaba(args.query, forzar_login=args.login)
    print(f"Captura guardada en: {archivo}")


if __name__ == "__main__":
    main()
