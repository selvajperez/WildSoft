from pathlib import Path

import diagnostico_precio

FIXTURE = (Path(__file__).parent / "fixtures" / "productlist_page19.html").read_text(encoding="utf-8")


def _preparar_archivo_pagina(tmp_path, monkeypatch, numero_pagina: int, html: str):
    dir_html = tmp_path / "paginas_html_crudo"
    dir_html.mkdir()
    (dir_html / f"productlist-{numero_pagina}.html").write_text(html, encoding="utf-8")
    monkeypatch.setattr(diagnostico_precio, "DIR_HTML_CRUDO", dir_html)


def test_buscar_producto_encuentra_por_texto_parcial_case_insensitive(tmp_path, monkeypatch):
    _preparar_archivo_pagina(tmp_path, monkeypatch, 19, FIXTURE)

    resultados = diagnostico_precio.buscar_producto("lavable sin bpa")

    assert len(resultados) == 1
    numero_pagina, item = resultados[0]
    assert numero_pagina == 19
    assert item["id"] == 1601487795601
    # Devuelve el item crudo, no el normalizado: conserva los campos originales
    # (incluido el espacio duro "\xa0" que trae el HTML real de Alibaba).
    assert "2.374,02" in item["fobPriceWithoutUnit"]
    assert item["priceFrom"] == "1.5"


def test_buscar_producto_sin_coincidencias_devuelve_vacio(tmp_path, monkeypatch):
    _preparar_archivo_pagina(tmp_path, monkeypatch, 19, FIXTURE)

    assert diagnostico_precio.buscar_producto("producto que no existe") == []


def test_buscar_producto_filtra_por_pagina(tmp_path, monkeypatch):
    _preparar_archivo_pagina(tmp_path, monkeypatch, 19, FIXTURE)

    assert diagnostico_precio.buscar_producto("lavable sin bpa", pagina=7) == []
    assert len(diagnostico_precio.buscar_producto("lavable sin bpa", pagina=19)) == 1
