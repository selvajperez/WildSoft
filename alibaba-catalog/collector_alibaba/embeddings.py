"""
Interfaz de embeddings de texto e imagen para Match Mode (ML <-> Alibaba).

Ajuste #4 aprobado por la usuaria: encapsular texto/imagen detrás de una
interfaz explícita para poder cambiar el modelo concreto más adelante sin
reescribir `matcher.py`. Dos familias de implementación:

  - `EmbedderTextoBolsaDePalabras` / `EmbedderImagenPorClaves`: livianas,
    determinísticas, sin red ni modelos pesados -- las que usan los tests
    de lógica pura (ranking, top_k, umbrales). No son semánticas: no hace
    falta que lo sean para probar la lógica del matcher, solo que
    respondan de forma controlada y reproducible.
  - `EmbedderTextoClip` / `EmbedderImagenClip`: `sentence-transformers`
    real, con carga perezosa -- el modelo (~cientos de MB) solo se
    descarga/carga la primera vez que se llama `.embed(...)`, nunca al
    importar el módulo. Así el resto de la suite de tests no se ve
    afectado por esta dependencia nueva ni por la falta de red.

Se elige un modelo CLIP multilingüe para texto (`clip-ViT-B-32-multilingual-v1`)
alineado al mismo espacio vectorial que el modelo CLIP de imagen
(`clip-ViT-B-32`): permite comparar el título de ML en español contra el
título/atributos de Alibaba en inglés por similitud de coseno directa, sin
un paso de traducción aparte para la señal de texto. La generación de la
query de búsqueda en Alibaba es un problema distinto (retrieval, no
matching) y se resuelve aparte -- ver `orquestador_matching.py`.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np


class EmbedderDeTexto(Protocol):
    def embed(self, texto: str) -> np.ndarray | None: ...


class EmbedderDeImagen(Protocol):
    def embed(self, url_imagen: str) -> np.ndarray | None: ...


def similitud_coseno(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """
    0.0 si falta cualquiera de los dos vectores (dato faltante, nunca se
    inventa una similitud) -- el llamador decide qué peso/confianza le da
    a una señal ausente, este helper no lo decide por él.
    """
    if a is None or b is None:
        return 0.0
    norma_a = np.linalg.norm(a)
    norma_b = np.linalg.norm(b)
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norma_a * norma_b))


_RE_PALABRA = re.compile(r"[a-záéíóúñü0-9]+")


class EmbedderTextoBolsaDePalabras:
    """
    Implementación liviana por hashing de palabras (bag-of-words),
    determinística y sin dependencias pesadas -- para tests de lógica
    pura del matcher. NO es semántica (no entiende sinónimos ni
    traducción entre idiomas): eso es trabajo del embedder real
    (`EmbedderTextoClip`). El matcher no sabe ni le importa cuál de las
    dos implementaciones está usando.
    """

    def __init__(self, dimensiones: int = 256):
        self.dimensiones = dimensiones

    def embed(self, texto: str) -> np.ndarray | None:
        if not texto:
            return None
        palabras = _RE_PALABRA.findall(texto.lower())
        if not palabras:
            return None
        vector = np.zeros(self.dimensiones)
        for palabra in palabras:
            indice = int(hashlib.md5(palabra.encode()).hexdigest(), 16) % self.dimensiones
            vector[indice] += 1.0
        return vector


class EmbedderImagenPorClaves:
    """
    Fake para tests: se construye con un dict explícito `{url: vector}`.
    Permite armar escenarios controlados ("estas dos imágenes son
    visualmente parecidas/distintas") sin descargar nada. Una URL no
    registrada devuelve `vector_por_defecto` (o None si no se pasó uno) --
    simula "no se pudo descargar/procesar esta imagen".
    """

    def __init__(self, vectores: dict[str, np.ndarray], vector_por_defecto: np.ndarray | None = None):
        self.vectores = vectores
        self.vector_por_defecto = vector_por_defecto

    def embed(self, url_imagen: str) -> np.ndarray | None:
        return self.vectores.get(url_imagen, self.vector_por_defecto)


_MODELO_TEXTO_CLIP = "clip-ViT-B-32-multilingual-v1"
_MODELO_IMAGEN_CLIP = "clip-ViT-B-32"


class EmbedderTextoClip:
    """
    Embedder de texto real vía `sentence-transformers`. Carga perezosa: el
    modelo se instancia recién en el primer `.embed(...)`, no en
    `__init__` -- para que construir este objeto en un script no descargue
    ni cargue nada hasta que de verdad haga falta.
    """

    def __init__(self, nombre_modelo: str = _MODELO_TEXTO_CLIP):
        self.nombre_modelo = nombre_modelo
        self._modelo = None

    def _cargar(self):
        if self._modelo is None:
            from sentence_transformers import SentenceTransformer

            self._modelo = SentenceTransformer(self.nombre_modelo)
        return self._modelo

    def embed(self, texto: str) -> np.ndarray | None:
        if not texto:
            return None
        return self._cargar().encode(texto, convert_to_numpy=True)


class EmbedderImagenClip:
    """
    Embedder de imagen real vía `sentence-transformers` (mismo espacio
    vectorial que `EmbedderTextoClip`). Descarga la imagen con `requests`
    (no Playwright: son URLs estáticas de CDN -- mlstatic.com, alicdn.com
    -- no páginas que necesiten un navegador real) y la decodifica con
    Pillow. Si la descarga o decodificación falla por cualquier motivo,
    devuelve None en vez de romper la corrida -- "imagen no disponible" es
    un resultado esperado, no una excepción no manejada.
    """

    def __init__(self, nombre_modelo: str = _MODELO_IMAGEN_CLIP, timeout_seg: float = 15.0):
        self.nombre_modelo = nombre_modelo
        self.timeout_seg = timeout_seg
        self._modelo = None

    def _cargar(self):
        if self._modelo is None:
            from sentence_transformers import SentenceTransformer

            self._modelo = SentenceTransformer(self.nombre_modelo)
        return self._modelo

    def embed(self, url_imagen: str) -> np.ndarray | None:
        if not url_imagen:
            return None
        try:
            import io

            import requests
            from PIL import Image

            respuesta = requests.get(url_imagen, timeout=self.timeout_seg)
            respuesta.raise_for_status()
            imagen = Image.open(io.BytesIO(respuesta.content)).convert("RGB")
        except Exception:
            return None
        return self._cargar().encode(imagen, convert_to_numpy=True)
