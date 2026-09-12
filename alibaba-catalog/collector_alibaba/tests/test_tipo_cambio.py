import requests

from tipo_cambio import URL_DOLAR_MEP, obtener_dolar_mep


class _RespuestaFake:
    def __init__(self, json_data, status=200):
        self._json_data = json_data
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status}")

    def json(self):
        return self._json_data


def test_obtener_dolar_mep_exitoso(monkeypatch):
    llamadas = []

    def get_fake(url, timeout):
        llamadas.append(url)
        return _RespuestaFake({"venta": 1050.5, "compra": 1040.0, "fechaActualizacion": "2026-09-12T10:00:00.000Z"})

    monkeypatch.setattr("tipo_cambio.requests.get", get_fake)

    resuelto = obtener_dolar_mep()

    assert resuelto.disponible is True
    assert resuelto.valor == 1050.5
    assert resuelto.fuente == URL_DOLAR_MEP
    assert resuelto.fecha_referencia == "2026-09-12T10:00:00.000Z"
    assert resuelto.obtenido_en is not None
    assert llamadas == [URL_DOLAR_MEP]  # una sola consulta, a una sola fuente


def test_obtener_dolar_mep_error_de_red_no_cae_a_otra_fuente(monkeypatch):
    llamadas = []

    def get_fake(url, timeout):
        llamadas.append(url)
        raise requests.exceptions.ConnectionError("no hay red")

    monkeypatch.setattr("tipo_cambio.requests.get", get_fake)

    resuelto = obtener_dolar_mep()

    assert resuelto.disponible is False
    assert resuelto.valor is None
    assert "no hay red" in resuelto.detalle
    assert llamadas == [URL_DOLAR_MEP]  # nunca reintenta con otra cotización/fuente


def test_obtener_dolar_mep_error_http(monkeypatch):
    monkeypatch.setattr("tipo_cambio.requests.get", lambda url, timeout: _RespuestaFake({}, status=500))

    resuelto = obtener_dolar_mep()

    assert resuelto.disponible is False
    assert resuelto.valor is None


def test_obtener_dolar_mep_respuesta_sin_campo_venta(monkeypatch):
    monkeypatch.setattr("tipo_cambio.requests.get", lambda url, timeout: _RespuestaFake({"compra": 1040.0}))

    resuelto = obtener_dolar_mep()

    assert resuelto.disponible is False
    assert resuelto.valor is None
    assert "venta" in resuelto.detalle.lower() or "valor" in resuelto.detalle.lower()


def test_obtener_dolar_mep_venta_no_numerica(monkeypatch):
    monkeypatch.setattr("tipo_cambio.requests.get", lambda url, timeout: _RespuestaFake({"venta": "no-numero"}))

    resuelto = obtener_dolar_mep()

    assert resuelto.disponible is False
    assert resuelto.valor is None


def test_obtener_dolar_mep_venta_cero_o_negativa_no_es_valida(monkeypatch):
    monkeypatch.setattr("tipo_cambio.requests.get", lambda url, timeout: _RespuestaFake({"venta": 0}))

    resuelto = obtener_dolar_mep()

    assert resuelto.disponible is False
