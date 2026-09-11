"""
Experimento controlado, aislado del pipeline: NO cambia
`parser_busqueda_ml.py` ni `orquestador_demanda_ml.py`, no escribe en
`candidatos_ml`/`historial_ml`, y NUNCA navega el link de tracking real
(`click1.mercadolibre.com.ar`).

Contexto: la medición de `medicion_confiabilidad_ml.py` mostró que la
URL reconstruida actual (`articulo.mercadolibre.com.ar/<item_id>`, sin
guion) falla siempre (0/31) para resultados que llegan envueltos en un
link de tracking. Investigando el HTML real de esos mismos `href` (sin
tocar el tracker), se encontró que ya traen un parámetro
`searchVariation=<ID>` en el fragmento -- en la mayoría de los casos con
el mismo formato "MLA"/"MLAU"+dígitos que ya usan las URLs directas
(100% confiables). Este script prueba, con navegación real controlada,
si `https://www.mercadolibre.com.ar/p/<searchVariation>?pdp_filters=item_id:<item_id>`
(sin slug) resuelve igual que el permalink completo real que sí conocemos
(`.../<slug>/p/<product_id>?pdp_filters=item_id:<item_id>`).

**Resultado del primer caso** (`MLA28873639`/`MLA1399281097`): 200 +
redirect automático al permalink completo, item_id correcto, extracción
normal. **Segunda ronda** (4 pares reales): 2/2 IDs con prefijo de 3
letras (`MLA`+dígitos) funcionaron igual con `/p/`; 3/3 IDs con prefijo
de 4 letras (`MLAU`+dígitos) dieron 404 con `/p/` pero funcionaron con
`/up/` en una tercera ronda -- 5/5 casos reales consistentes en total.
**Ya incorporado como estrategia real** en
`parser_busqueda_ml.segmento_ruta_producto_id`/`_url_desde_search_variation`,
reutilizados acá en vez de duplicarse.

Por cada par (product_id, item_id) reporta:
  - status HTTP de la navegación inicial
  - si hubo redirect y cuál es la URL final
  - si la ficha resultante es el 404 real de ML
  - si el item_id esperado aparece en el HTML final (indicio de que ML
    resolvió la ficha del listado correcto, no otra variante del mismo
    producto de catálogo)
  - si se puede extraer precio y/o unidades vendidas normalmente

Uso:
    python experimento_url_producto_reconstruida.py
    python experimento_url_producto_reconstruida.py --par MLA28873639:MLA1399281097 --par MLAU3739976006:MLA2789721006
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from navegador_ml import (  # noqa: E402
    bloqueado_ml_heuristico,
    confirmar_login_manual,
    contenido_seguro,
    es_desafio_pow_ml,
    es_primera_vez,
    esperar_resolucion_desafio_pow,
    navegador_persistente,
    pausar_por_bloqueo_y_continuar,
)
from parser_busqueda_ml import segmento_ruta_producto_id  # noqa: E402
from parser_ficha_ml import parsear_ficha_ml  # noqa: E402

URL_BASE_ML = "https://listado.mercadolibre.com.ar"

# El primer caso real investigado: badge "MÁS VENDIDO", href de tracking
# con searchVariation=MLA28873639 y pdp_filters=item_id:MLA1399281097.
PARES_DEFAULT = [("MLA28873639", "MLA1399281097")]

DIR_REPORTES = Path(__file__).parent.parent / "medicion_confiabilidad_ml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "experimento_url_producto_reconstruida.log")],
)
logger = logging.getLogger("experimento_url_producto_reconstruida")


def _construir_url(product_id: str, item_id: str) -> str:
    segmento = segmento_ruta_producto_id(product_id)
    return f"https://www.mercadolibre.com.ar/{segmento}/{product_id}?pdp_filters=item_id:{item_id}"


def _navegar_y_diagnosticar(pagina, url: str, etiqueta: str) -> tuple[int | None, str, str]:
    """
    Variante de `navegador_ml.abrir_pagina_ml` que además devuelve el
    status HTTP de la navegación inicial y la URL final (después de
    cualquier redirect real de Mercado Libre) -- información que
    `abrir_pagina_ml` no expone porque el pipeline no la necesita.
    """
    respuesta = pagina.goto(url, wait_until="domcontentloaded")
    status = respuesta.status if respuesta else None
    html = contenido_seguro(pagina)

    if es_desafio_pow_ml(html):
        logger.info("Desafío PoW detectado en '%s'; esperando resolución automática...", etiqueta)
        html = esperar_resolucion_desafio_pow(pagina)

    if bloqueado_ml_heuristico(html):
        html = pausar_por_bloqueo_y_continuar(pagina, url, etiqueta)

    return status, pagina.url, html


def _diagnosticar(product_id: str, item_id: str, url_pedida: str, status: int | None, url_final: str, html: str) -> dict:
    """
    Lógica pura (sin navegador) que arma el resultado del experimento a
    partir de lo que ya se obtuvo navegando. Separada de `probar_par` para
    poder probarla con HTML real ya capturado, sin necesitar Chrome.
    """
    datos_ficha = parsear_ficha_ml(html, url=url_final)

    return {
        "product_id": product_id,
        "item_id_esperado": item_id,
        "url_pedida": url_pedida,
        "status_http": status,
        "hubo_redirect": url_final != url_pedida,
        "url_final": url_final,
        "es_404_real_ml": datos_ficha["pagina_no_encontrada"],
        "item_id_esperado_presente_en_html": item_id.upper() in html.upper(),
        "nombre_extraido": datos_ficha["nombre"],
        "precio_ml": datos_ficha["precio_ml"],
        "unidades_vendidas": datos_ficha["unidades_vendidas"],
        "cantidad_opiniones": datos_ficha["cantidad_opiniones"],
        "rating": datos_ficha["rating"],
        "extraccion_normal": not datos_ficha["pagina_no_encontrada"] and (
            datos_ficha["precio_ml"] is not None or datos_ficha["unidades_vendidas"] is not None
        ),
    }


def probar_par(pagina, product_id: str, item_id: str) -> dict:
    url_pedida = _construir_url(product_id, item_id)
    logger.info("Probando: %s", url_pedida)

    status, url_final, html = _navegar_y_diagnosticar(pagina, url_pedida, f"experimento {product_id}/{item_id}")
    resultado = _diagnosticar(product_id, item_id, url_pedida, status, url_final, html)

    logger.info("Resultado %s/%s: %s", product_id, item_id, resultado)
    return resultado


def ejecutar_experimento(pares: list[tuple[str, str]], forzar_login: bool = False) -> list[dict]:
    primera_vez = es_primera_vez()
    resultados = []

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_BASE_ML, wait_until="domcontentloaded")
            confirmar_login_manual()

        for product_id, item_id in pares:
            resultados.append(probar_par(pagina, product_id, item_id))

    return resultados


def _guardar_reporte(resultados: list[dict]) -> Path:
    DIR_REPORTES.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archivo = DIR_REPORTES / f"experimento_url_reconstruida_{timestamp}.json"
    archivo.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    return archivo


def _imprimir_resultados(resultados: list[dict]) -> None:
    for r in resultados:
        print(f"\n--- {r['product_id']} / {r['item_id_esperado']} ---")
        print(f"URL pedida:        {r['url_pedida']}")
        print(f"Status HTTP:       {r['status_http']}")
        print(f"Hubo redirect:     {r['hubo_redirect']}")
        print(f"URL final:         {r['url_final']}")
        print(f"Es 404 real de ML: {r['es_404_real_ml']}")
        print(f"item_id esperado presente en el HTML final: {r['item_id_esperado_presente_en_html']}")
        print(f"Nombre extraído:   {r['nombre_extraido']}")
        print(f"Precio / vendidas: {r['precio_ml']} / {r['unidades_vendidas']}")
        print(f"Extracción normal (precio y/o ventas, sin 404): {r['extraccion_normal']}")


def main() -> None:
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument(
        "--par", action="append", dest="pares", metavar="PRODUCT_ID:ITEM_ID",
        help="Par product_id:item_id a probar (repetible). Sin ninguno, usa el caso default (MLA28873639:MLA1399281097).",
    )
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    args = argparser.parse_args()

    if args.pares:
        pares = [tuple(p.split(":", 1)) for p in args.pares]
    else:
        pares = PARES_DEFAULT

    resultados = ejecutar_experimento(pares, forzar_login=args.login)
    archivo = _guardar_reporte(resultados)

    _imprimir_resultados(resultados)
    print(f"\nReporte completo guardado en: {archivo}")


if __name__ == "__main__":
    main()
