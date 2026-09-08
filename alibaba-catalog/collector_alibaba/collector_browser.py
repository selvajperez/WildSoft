"""
Orquesta la recolección del catálogo usando un Chrome real y visible,
controlado por Playwright con un perfil de datos dedicado y persistente.

Pensado para cuando el scraping por HTTP puro (`collector.py`/`scraper.py`)
es bloqueado por el CAPTCHA "punish" de Alibaba: acá la navegación la hace
un navegador real, con la sesión que la usuaria inicia manualmente una
sola vez (queda guardada en el perfil dedicado para corridas futuras).

No resuelve ni evade CAPTCHAs: si aparece uno, el collector se detiene,
avisa, y deja la ventana de Chrome abierta para que la usuaria decida qué
hacer. El progreso (qué páginas ya se recorrieron) queda guardado en la
base, así que una corrida posterior retoma donde quedó sin repetir
páginas ya hechas.

Cada página visitada se archiva tal cual (HTML crudo, antes de parsear)
en `paginas_html_crudo/`, para poder diagnosticar o reprocesar el catálogo
sin volver a navegar Alibaba si algún campo se interpretó mal.

Uso (ver también README.md):
    python collector_browser.py               # corrida normal
    python collector_browser.py --login        # forzar login manual de nuevo
    python collector_browser.py --reiniciar-progreso   # re-recorrer todo
    python collector_browser.py --recuperar-html 1-14  # solo archivar HTML de esas páginas,
                                                          # sin tocar el progreso guardado
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

from playwright.sync_api import sync_playwright  # noqa: E402

from parser import parsear_categorias, parsear_pagina_listado  # noqa: E402
from scraper import PaginaBloqueadaError, contiene_marcadores_bloqueo  # noqa: E402
import db  # noqa: E402

URL_BASE = "https://dcsjry888.m.en.alibaba.com"
URL_PRIMERA_PAGINA = f"{URL_BASE}/productlist-1.html?filter=all&sortType=modified-desc"

# Perfil de Chrome separado del habitual de la usuaria: se loguea una vez
# acá y la sesión queda guardada para las corridas siguientes, sin tocar
# ni depender del Chrome de todos los días.
PERFIL_DEDICADO = Path(__file__).parent.parent / ".perfil_chrome_collector"

# Archivo del HTML crudo de cada página visitada, tal cual lo devuelve el
# navegador, antes de parsearlo. `parser.py` solo se queda con los campos
# ya normalizados; sin este archivo, un campo del JSON original mal
# interpretado (como el bug de `priceFrom` de septiembre 2026) no se puede
# diagnosticar ni reprocesar después sin volver a navegar Alibaba.
DIR_HTML_CRUDO = Path(__file__).parent.parent / "paginas_html_crudo"

DELAY_ENTRE_PAGINAS_SEG = (1.5, 3.0)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "collector_browser.log")],
)
logger = logging.getLogger("collector_alibaba_browser")


def _url_pagina(formato_url: str, pagina: int) -> str:
    return URL_BASE + formato_url.format(pagina)


def _esperar_entre_paginas() -> None:
    time.sleep(random.uniform(*DELAY_ENTRE_PAGINAS_SEG))


def _paginas_pendientes(total_paginas: int, completadas: set[int]) -> list[int]:
    """Páginas de 1 a `total_paginas` que todavía no están en `completadas`."""
    return [pagina for pagina in range(1, total_paginas + 1) if pagina not in completadas]


def _guardar_html_crudo(pagina: int, html: str) -> None:
    DIR_HTML_CRUDO.mkdir(parents=True, exist_ok=True)
    (DIR_HTML_CRUDO / f"productlist-{pagina}.html").write_text(html, encoding="utf-8")


def _parsear_rango_paginas(texto: str) -> list[int]:
    """'1-14' -> [1..14]; '3' -> [3]; '1,3,5-7' -> [1,3,5,6,7] (sin duplicados, ordenado)."""
    paginas: set[int] = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            inicio_str, fin_str = parte.split("-", 1)
            inicio, fin = int(inicio_str), int(fin_str)
            paginas.update(range(inicio, fin + 1))
        else:
            paginas.add(int(parte))
    return sorted(paginas)


def _confirmar_login_manual() -> None:
    print("\n" + "=" * 70)
    print("Se abrió Chrome con un perfil dedicado para este collector.")
    print("Iniciá sesión en Alibaba manualmente en esa ventana (si hace falta).")
    print("La sesión queda guardada en ese perfil: en corridas futuras no")
    print("debería volver a pedirte esto, salvo que uses --login de nuevo.")
    print("=" * 70)
    input("Cuando termines de iniciar sesión, volvé a esta terminal y presioná ENTER para continuar...")


def _pausar_por_bloqueo(url: str, pagina: int) -> None:
    logger.error("Bloqueo (CAPTCHA) detectado en la página %d (%s).", pagina, url)
    print("\n" + "!" * 70)
    print(f"CAPTCHA / bloqueo detectado en la página {pagina}.")
    print("El collector se detiene ACÁ: no resuelve ni evade el CAPTCHA automáticamente.")
    print("La ventana de Chrome se queda abierta para que la mires o la resuelvas vos si querés.")
    if pagina > 1:
        print(f"El progreso hasta la página {pagina - 1} ya quedó guardado en la base.")
    print("Podés volver a correr el collector más tarde: retoma desde acá, sin repetir páginas ya hechas.")
    print("Cuando quieras cerrar el collector (y con él, esta ventana de Chrome), volvé acá y presioná ENTER.")
    print("!" * 70 + "\n")
    input()


def recolectar_catalogo_navegador(
    url_inicial: str = URL_PRIMERA_PAGINA,
    max_paginas: int | None = None,
    forzar_login: bool = False,
) -> int:
    """
    Recorre el listado completo con un Chrome real (Playwright + perfil
    persistente) y persiste los productos. Devuelve la cantidad total de
    productos guardados (tras deduplicar por URL).
    """
    conexion = db.conectar()
    es_primera_vez = not PERFIL_DEDICADO.exists()

    with sync_playwright() as p:
        contexto = p.chromium.launch_persistent_context(
            user_data_dir=str(PERFIL_DEDICADO),
            channel="chrome",
            headless=False,
        )
        try:
            pagina_navegador = contexto.pages[0] if contexto.pages else contexto.new_page()

            if es_primera_vez or forzar_login:
                pagina_navegador.goto(url_inicial, wait_until="domcontentloaded")
                _confirmar_login_manual()

            logger.info("Descargando página 1 (navegador) para conocer categorías y paginación real...")
            pagina_navegador.goto(url_inicial, wait_until="domcontentloaded")
            html_pagina_1 = pagina_navegador.content()
            _guardar_html_crudo(1, html_pagina_1)

            if contiene_marcadores_bloqueo(html_pagina_1):
                _pausar_por_bloqueo(url_inicial, 1)
                raise PaginaBloqueadaError(f"Bloqueo detectado en {url_inicial}")

            categorias = parsear_categorias(html_pagina_1)
            productos_pagina_1, paginacion = parsear_pagina_listado(html_pagina_1, categorias)

            if paginacion is None:
                logger.error(
                    "No se pudo leer la paginación en %s; el sitio puede haber cambiado de estructura.",
                    url_inicial,
                )
                raise SystemExit(1)

            total_paginas = paginacion.total_paginas
            if max_paginas is not None:
                total_paginas = min(total_paginas, max_paginas)

            completadas_antes = {p for p in db.obtener_paginas_completadas(conexion) if p <= total_paginas}

            db.upsert_productos(conexion, productos_pagina_1)
            db.marcar_pagina_completada(conexion, 1)
            logger.info(
                "Catálogo: %d productos declarados, %d por página, %d páginas a recorrer.",
                paginacion.total_productos, paginacion.productos_por_pagina, total_paginas,
            )

            if completadas_antes:
                logger.info(
                    "Retomando progreso guardado: %d de %d páginas ya estaban completas.",
                    len(completadas_antes), total_paginas,
                )

            pendientes = _paginas_pendientes(total_paginas, db.obtener_paginas_completadas(conexion))

            for numero_pagina in pendientes:
                _esperar_entre_paginas()
                url = _url_pagina(paginacion.formato_url, numero_pagina)
                pagina_navegador.goto(url, wait_until="domcontentloaded")
                html = pagina_navegador.content()
                _guardar_html_crudo(numero_pagina, html)

                if contiene_marcadores_bloqueo(html):
                    _pausar_por_bloqueo(url, numero_pagina)
                    raise PaginaBloqueadaError(f"Bloqueo detectado en la página {numero_pagina} ({url})")

                productos_pagina, _ = parsear_pagina_listado(html, categorias)
                if not productos_pagina:
                    logger.info("Página %d sin productos; se asume fin del catálogo.", numero_pagina)
                    break

                db.upsert_productos(conexion, productos_pagina)
                db.marcar_pagina_completada(conexion, numero_pagina)
                logger.info("Página %d/%d: %d productos.", numero_pagina, total_paginas, len(productos_pagina))
        finally:
            contexto.close()

    total_guardado = db.contar_productos(conexion)
    logger.info("Total de productos únicos en la base: %d", total_guardado)
    return total_guardado


def recuperar_html_paginas(paginas: list[int], forzar_login: bool = False) -> None:
    """
    Vuelve a visitar páginas puntuales solo para archivar su HTML crudo en
    `paginas_html_crudo/` (ej. para recuperar el dato crudo de páginas ya
    completadas cuando se detectó un bug de parseo después de recorrerlas).

    A propósito NO toca `progreso_paginas`: no marca páginas como
    completadas, así que no puede alterar ni desmarcar el progreso que ya
    existe. `recolectar_catalogo_navegador` sigue siendo la única función
    que avanza ese checkpoint. Sí reutiliza el parser para refrescar
    `productos_alibaba` (upsert, deduplicado por URL) como efecto
    secundario útil, pero eso tampoco toca el progreso.
    """
    if not paginas:
        return

    conexion = db.conectar()
    es_primera_vez = not PERFIL_DEDICADO.exists()

    with sync_playwright() as p:
        contexto = p.chromium.launch_persistent_context(
            user_data_dir=str(PERFIL_DEDICADO),
            channel="chrome",
            headless=False,
        )
        try:
            pagina_navegador = contexto.pages[0] if contexto.pages else contexto.new_page()

            if es_primera_vez or forzar_login:
                pagina_navegador.goto(URL_PRIMERA_PAGINA, wait_until="domcontentloaded")
                _confirmar_login_manual()

            # Página 1 hace falta siempre para conocer categorías y el
            # patrón de paginación real, aunque no esté en `paginas`.
            logger.info("Descargando página 1 para conocer categorías y paginación (progreso NO modificado)...")
            pagina_navegador.goto(URL_PRIMERA_PAGINA, wait_until="domcontentloaded")
            html_pagina_1 = pagina_navegador.content()

            if contiene_marcadores_bloqueo(html_pagina_1):
                _pausar_por_bloqueo(URL_PRIMERA_PAGINA, 1)
                raise PaginaBloqueadaError(f"Bloqueo detectado en {URL_PRIMERA_PAGINA}")

            categorias = parsear_categorias(html_pagina_1)
            productos_pagina_1, paginacion = parsear_pagina_listado(html_pagina_1, categorias)

            if paginacion is None:
                logger.error("No se pudo leer la paginación en %s.", URL_PRIMERA_PAGINA)
                raise SystemExit(1)

            if 1 in paginas:
                _guardar_html_crudo(1, html_pagina_1)
                db.upsert_productos(conexion, productos_pagina_1)
                logger.info("Página 1: HTML archivado y productos refrescados (progreso NO modificado).")

            for numero_pagina in paginas:
                if numero_pagina == 1:
                    continue

                _esperar_entre_paginas()
                url = _url_pagina(paginacion.formato_url, numero_pagina)
                pagina_navegador.goto(url, wait_until="domcontentloaded")
                html = pagina_navegador.content()

                if contiene_marcadores_bloqueo(html):
                    _pausar_por_bloqueo(url, numero_pagina)
                    raise PaginaBloqueadaError(f"Bloqueo detectado en la página {numero_pagina} ({url})")

                _guardar_html_crudo(numero_pagina, html)
                productos_pagina, _ = parsear_pagina_listado(html, categorias)
                db.upsert_productos(conexion, productos_pagina)
                logger.info(
                    "Página %d: HTML archivado y %d productos refrescados (progreso NO modificado).",
                    numero_pagina, len(productos_pagina),
                )
        finally:
            contexto.close()

    logger.info("Recuperación de HTML crudo terminada para las páginas: %s", paginas)


def main() -> None:
    argparser = argparse.ArgumentParser(description="Collector de catálogo Alibaba vía Chrome real (Playwright).")
    argparser.add_argument(
        "--login", action="store_true",
        help="Forzar el paso de login manual aunque el perfil ya exista (por ejemplo, si la sesión expiró).",
    )
    argparser.add_argument(
        "--reiniciar-progreso", action="store_true",
        help="Olvidar qué páginas ya se completaron y volver a recorrerlas todas (no borra productos ya guardados).",
    )
    argparser.add_argument(
        "--max-paginas", type=int, default=None,
        help="Límite de páginas a recorrer (útil para probar con pocas antes de correr las 28 completas).",
    )
    argparser.add_argument(
        "--recuperar-html", type=str, default=None, metavar="RANGO",
        help=(
            "Volver a visitar páginas puntuales SOLO para archivar su HTML crudo "
            "(ej. '1-14' o '3,5,7-9'). No toca el progreso guardado: no marca ni "
            "desmarca páginas como completadas. Ignora --reiniciar-progreso."
        ),
    )
    args = argparser.parse_args()

    if args.recuperar_html:
        paginas = _parsear_rango_paginas(args.recuperar_html)
        try:
            recuperar_html_paginas(paginas, forzar_login=args.login)
        except PaginaBloqueadaError:
            sys.exit(1)
        return

    if args.reiniciar_progreso:
        conexion = db.conectar()
        db.reiniciar_progreso(conexion)
        conexion.close()
        logger.info("Progreso reiniciado: la próxima corrida vuelve a recorrer todas las páginas.")

    try:
        recolectar_catalogo_navegador(forzar_login=args.login, max_paginas=args.max_paginas)
    except PaginaBloqueadaError:
        sys.exit(1)


if __name__ == "__main__":
    main()
