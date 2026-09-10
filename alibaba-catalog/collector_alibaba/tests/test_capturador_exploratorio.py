import json

import capturador_exploratorio as ce


def test_bloqueado_ml_heuristico_detecta_marcadores_provisorios():
    assert ce.bloqueado_ml_heuristico("<html>Por favor completá el CAPTCHA</html>") is True
    assert ce.bloqueado_ml_heuristico("<html>Verificación de seguridad requerida</html>") is True


def test_bloqueado_ml_heuristico_no_marca_html_normal():
    assert ce.bloqueado_ml_heuristico("<html><body>Resultados de la búsqueda</body></html>") is False


def test_extraer_primer_link_producto_ml_encuentra_patron_mla():
    html = '<a href="https://articulo.mercadolibre.com.ar/MLA-123456789-candado-_JM">Candado</a>'
    assert ce._extraer_primer_link_producto_ml(html) == (
        "https://articulo.mercadolibre.com.ar/MLA-123456789-candado-_JM"
    )


def test_extraer_primer_link_producto_ml_devuelve_none_si_no_hay_patron():
    assert ce._extraer_primer_link_producto_ml("<html><body>nada</body></html>") is None


def test_guardar_html_escribe_archivo_con_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "DIR_CAPTURAS", tmp_path / "capturas")

    archivo = ce._guardar_html("ml_busqueda", "<html>contenido</html>")

    assert archivo.exists()
    assert archivo.name.startswith("ml_busqueda_")
    assert archivo.read_text(encoding="utf-8") == "<html>contenido</html>"


def test_registrar_captura_agrega_una_linea_jsonl(tmp_path, monkeypatch):
    dir_capturas = tmp_path / "capturas"
    monkeypatch.setattr(ce, "DIR_CAPTURAS", dir_capturas)
    monkeypatch.setattr(ce, "MANIFIESTO", dir_capturas / "manifiesto.jsonl")

    ce._registrar_captura("ml_busqueda", "https://ejemplo.test", tmp_path / "x.html", bloqueado=False)
    ce._registrar_captura("ml_ficha", "(no encontrado)", None, bloqueado=False)

    lineas = (dir_capturas / "manifiesto.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2

    primera = json.loads(lineas[0])
    assert primera["etiqueta"] == "ml_busqueda"
    assert primera["url"] == "https://ejemplo.test"
    assert primera["archivo"] == "x.html"
    assert primera["bloqueado"] is False

    segunda = json.loads(lineas[1])
    assert segunda["archivo"] is None
