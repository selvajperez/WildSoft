"""
Match Mode: decide si un producto de Alibaba es el mismo producto (o
sustancialmente equivalente) que un candidato de Mercado Libre con
demanda confirmada -- no busca el "más parecido", busca uno confiablemente
comparable, o declara explícitamente que no lo hay
(`SIN_MATCH_CONFIABLE`). Diseño aprobado por la usuaria con 5 ajustes (ver
ESTADO_ACTUAL.md para el detalle completo de la discusión).

Dos etapas, para no pagar el costo de abrir la ficha individual de cada
resultado de búsqueda:

  1. `rankear_candidatos`: ranking barato con los datos YA disponibles en
     el listado de búsqueda (título + miniatura) contra el producto de
     ML. Se queda con el `top_k` (default 3, configurable -- ajuste #1).
  2. `verificar_candidatos`: abre la ficha individual de cada uno de esos
     `top_k`, EN ORDEN, y recién ahí suma la señal de atributos
     estructurados + fotos reales del proveedor. Se detiene en el primer
     candidato que no queda vetado por una incompatibilidad esencial y
     alcanza el umbral de match -- si el candidato #1 revela una
     incompatibilidad dura (o simplemente no alcanza el umbral), se
     prueba el #2, después el #3. Solo se devuelve `SIN_MATCH_CONFIABLE`
     después de agotar los candidatos verificables del top_k (ajuste #1).

Las tres señales (ajuste #4: cada una detrás de la interfaz de
`embeddings.py`, intercambiable sin tocar este módulo):

  - texto: similitud de coseno entre el nombre+descripción de ML y el
    nombre de Alibaba (título de listado en el ranking barato, `subject`
    real de la ficha en la verificación).
  - imagen: similitud de coseno entre la imagen de ML y la(s) imagen(es)
    de Alibaba -- en la verificación se compara contra TODAS las fotos de
    la ficha (`mediaItems`) y se toma la mejor, no solo la primera.
  - atributos: ver `atributos_matching.py`. Una incompatibilidad DURA acá
    (atributo esencial, ambos lados con valor confiable, incompatibles)
    vetea el candidato sin importar cuán alto sea el texto/imagen --
    requisito explícito de la usuaria ("una similitud visual alta con una
    especificación esencial incompatible debe poder impedir un match").
    Si no hay evidencia de atributos de ningún lado, esta señal queda
    neutral (no premia ni penaliza) y el score se re-normaliza sobre
    texto+imagen únicamente.

Precio, MOQ, `proveedor_verificado` y `es_publicidad` del listado de
Alibaba NUNCA entran en el cálculo de similitud -- son señales de calidad
comercial para una etapa posterior (filtro económico, todavía sin
empezar), no de si el producto es el mismo (regla explícita de la
usuaria).

Pesos y umbrales (`PesosMatching`/`UmbralesMatching`) son valores
iniciales razonables, NO calibrados -- ajuste #5: se calibran con la
validación real, se pasan como parámetro en vez de quedar hardcodeados.

La generación de la query de búsqueda en Alibaba es responsabilidad de
quien llama (`orquestador_matching.py`), no de este módulo -- ajuste #3:
retrieval y matching son problemas distintos. Este módulo nunca concluye
"no existe match" solo porque la lista de candidatos vino vacía; lo dice
explícitamente en el motivo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from atributos_matching import (
    AtributoExtraido,
    ComparacionAtributo,
    comparar_atributos,
    extraer_atributos_alibaba,
    extraer_atributos_texto_libre,
    incompatibilidad_esencial,
    score_atributos,
)
from embeddings import EmbedderDeImagen, EmbedderDeTexto, similitud_coseno
from parser_ficha_alibaba import parsear_ficha_alibaba

CATEGORIAS = ("MATCH_ALTO", "MATCH_PROBABLE", "SIN_MATCH_CONFIABLE")

TOP_K_DEFAULT = 3


@dataclass
class PesosMatching:
    texto: float = 0.45
    imagen: float = 0.35
    atributos: float = 0.20


@dataclass
class UmbralesMatching:
    match_alto: float = 0.80
    match_probable: float = 0.60


@dataclass
class ProductoMLParaMatching:
    id_ml: str
    nombre: str
    descripcion: str | None = None
    imagen_url: str | None = None

    def texto_para_matching(self) -> str:
        return " ".join(parte for parte in (self.nombre, self.descripcion) if parte)


@dataclass
class CandidatoAlibabaListado:
    """Lo que ya se sabe de un resultado de búsqueda sin abrir su ficha (ver parser_busqueda_alibaba.py)."""

    id_alibaba: str
    url_alibaba: str
    nombre: str | None
    imagen_url: str | None
    posicion: int


@dataclass
class CandidatoRankeado:
    candidato: CandidatoAlibabaListado
    texto_score: float
    imagen_score: float
    score_ranking: float


@dataclass
class CandidatoVerificado:
    candidato_listado: CandidatoAlibabaListado
    url_alibaba: str
    nombre_alibaba: str | None
    texto_score: float
    imagen_score: float
    atributos_score: float
    atributos_cobertura: float
    comparaciones_atributos: list[ComparacionAtributo]
    veto: ComparacionAtributo | None
    score_final: float
    categoria: str
    motivo: str


@dataclass
class MatchResult:
    id_ml: str
    query_usada: str
    categoria: str
    candidato_elegido: CandidatoVerificado | None
    candidatos_rankeados: list[CandidatoRankeado]
    candidatos_evaluados: list[CandidatoVerificado]
    motivo: str


def _combinar_score(
    texto_score: float,
    imagen_score: float,
    imagen_disponible: bool,
    atributos_score: float,
    cobertura_atributos: float,
    pesos: PesosMatching,
) -> float:
    """
    Re-normaliza el peso sobre las señales que de verdad se pudieron
    comparar. Texto siempre cuenta (siempre hay al menos un nombre de
    cada lado). Atributos se excluye si no hubo ningún atributo
    comparable de ningún lado (`cobertura_atributos == 0`) -- ya
    validado. Imagen se excluye si `imagen_disponible=False` -- hallazgo
    real de la validación (Casos 1, 2 y 4: la ficha de ML no siempre
    expone una foto): antes, la ausencia de imagen contaba como "muy
    distinta" a valor 0.0 con el peso completo (35%), arrastrando el
    score hacia abajo sin ninguna evidencia real de que las imágenes
    fueran distintas -- ahora, igual que con atributos, la señal
    ausente simplemente no participa del promedio ponderado.
    """
    señales = [("texto", texto_score, pesos.texto)]
    if imagen_disponible:
        señales.append(("imagen", imagen_score, pesos.imagen))
    if cobertura_atributos > 0:
        señales.append(("atributos", atributos_score, pesos.atributos))

    total_pesos = sum(peso for _, _, peso in señales)
    if total_pesos == 0:
        return 0.0
    return sum(valor * peso for _, valor, peso in señales) / total_pesos


def _categorizar(score: float, umbrales: UmbralesMatching) -> str:
    if score >= umbrales.match_alto:
        return "MATCH_ALTO"
    if score >= umbrales.match_probable:
        return "MATCH_PROBABLE"
    return "SIN_MATCH_CONFIABLE"


def rankear_candidatos(
    producto_ml: ProductoMLParaMatching,
    candidatos: list[CandidatoAlibabaListado],
    embedder_texto: EmbedderDeTexto,
    embedder_imagen: EmbedderDeImagen,
    top_k: int = TOP_K_DEFAULT,
    pesos: PesosMatching | None = None,
) -> list[CandidatoRankeado]:
    """
    Ranking barato: solo texto + imagen de listado (los atributos
    estructurados recién están disponibles al abrir la ficha). Devuelve
    los `top_k` mejor rankeados, de mayor a menor score -- nunca abre
    ninguna ficha.
    """
    pesos = pesos or PesosMatching()
    vector_texto_ml = embedder_texto.embed(producto_ml.texto_para_matching())
    vector_imagen_ml = embedder_imagen.embed(producto_ml.imagen_url) if producto_ml.imagen_url else None

    rankeados = []
    for candidato in candidatos:
        texto_score = similitud_coseno(vector_texto_ml, embedder_texto.embed(candidato.nombre or ""))
        vector_imagen_candidato = embedder_imagen.embed(candidato.imagen_url) if candidato.imagen_url else None
        imagen_disponible = vector_imagen_ml is not None and vector_imagen_candidato is not None
        imagen_score = similitud_coseno(vector_imagen_ml, vector_imagen_candidato) if imagen_disponible else 0.0
        score_ranking = _combinar_score(texto_score, imagen_score, imagen_disponible, 0.0, 0.0, pesos)
        rankeados.append(CandidatoRankeado(candidato, texto_score, imagen_score, score_ranking))

    rankeados.sort(key=lambda r: r.score_ranking, reverse=True)
    return rankeados[:top_k]


def verificar_candidatos(
    producto_ml: ProductoMLParaMatching,
    atributos_ml: dict[str, AtributoExtraido],
    rankeados: list[CandidatoRankeado],
    abrir_ficha: Callable[[str], str],
    embedder_texto: EmbedderDeTexto,
    embedder_imagen: EmbedderDeImagen,
    pesos: PesosMatching | None = None,
    umbrales: UmbralesMatching | None = None,
    tolerancias_atributos: dict[str, float] | None = None,
) -> tuple[list[CandidatoVerificado], CandidatoVerificado | None]:
    """
    Abre las fichas de `rankeados` EN ORDEN (ajuste #1). Se detiene en el
    primer candidato que no queda vetado por una incompatibilidad
    esencial y cuya categoría final es MATCH_ALTO o MATCH_PROBABLE.
    `abrir_ficha(url) -> html` es inyectado para poder probar todo el
    flujo con HTML ya capturado, sin navegador real.

    Devuelve (evaluados, elegido). `evaluados` siempre incluye TODOS los
    candidatos que se llegaron a abrir (auditable aunque no haya match),
    `elegido` es None si se agotó el top_k sin encontrar uno confiable.
    """
    pesos = pesos or PesosMatching()
    umbrales = umbrales or UmbralesMatching()

    evaluados: list[CandidatoVerificado] = []
    elegido: CandidatoVerificado | None = None
    vector_imagen_ml = embedder_imagen.embed(producto_ml.imagen_url) if producto_ml.imagen_url else None
    vector_texto_ml = embedder_texto.embed(producto_ml.texto_para_matching())

    for rankeado in rankeados:
        html = abrir_ficha(rankeado.candidato.url_alibaba)
        datos_ficha = parsear_ficha_alibaba(html, url=rankeado.candidato.url_alibaba)

        nombre_alibaba = datos_ficha.get("nombre_ficha") or rankeado.candidato.nombre or ""
        texto_score = similitud_coseno(vector_texto_ml, embedder_texto.embed(nombre_alibaba))

        imagenes_alibaba = datos_ficha.get("imagenes") or (
            [rankeado.candidato.imagen_url] if rankeado.candidato.imagen_url else []
        )
        vectores_imagenes_alibaba = [v for v in (embedder_imagen.embed(url) for url in imagenes_alibaba) if v is not None]
        imagen_disponible = vector_imagen_ml is not None and bool(vectores_imagenes_alibaba)
        imagen_score = (
            max(similitud_coseno(vector_imagen_ml, v) for v in vectores_imagenes_alibaba)
            if imagen_disponible
            else 0.0
        )

        atributos_alibaba = extraer_atributos_alibaba(datos_ficha.get("atributos"), texto_extra=nombre_alibaba)
        comparaciones = comparar_atributos(atributos_ml, atributos_alibaba, tolerancias_atributos)
        atributos_score, cobertura = score_atributos(comparaciones)
        veto = incompatibilidad_esencial(comparaciones)

        score_final = _combinar_score(texto_score, imagen_score, imagen_disponible, atributos_score, cobertura, pesos)

        if veto is not None:
            categoria = "SIN_MATCH_CONFIABLE"
            motivo = f"Vetado por atributo esencial incompatible ('{veto.tipo}': {veto.detalle})."
        else:
            categoria = _categorizar(score_final, umbrales)
            motivo = (
                f"Score combinado {score_final:.2f} -- texto {texto_score:.2f}, imagen {imagen_score:.2f}, "
                f"atributos {atributos_score:.2f} (cobertura {cobertura:.0%})."
            )

        candidato_verificado = CandidatoVerificado(
            candidato_listado=rankeado.candidato,
            url_alibaba=rankeado.candidato.url_alibaba,
            nombre_alibaba=nombre_alibaba or None,
            texto_score=texto_score,
            imagen_score=imagen_score,
            atributos_score=atributos_score,
            atributos_cobertura=cobertura,
            comparaciones_atributos=comparaciones,
            veto=veto,
            score_final=score_final,
            categoria=categoria,
            motivo=motivo,
        )
        evaluados.append(candidato_verificado)

        if categoria in ("MATCH_ALTO", "MATCH_PROBABLE"):
            elegido = candidato_verificado
            break

    return evaluados, elegido


def ejecutar_matching(
    producto_ml: ProductoMLParaMatching,
    query_usada: str,
    candidatos_listado: list[CandidatoAlibabaListado],
    abrir_ficha: Callable[[str], str],
    embedder_texto: EmbedderDeTexto,
    embedder_imagen: EmbedderDeImagen,
    top_k: int = TOP_K_DEFAULT,
    pesos: PesosMatching | None = None,
    umbrales: UmbralesMatching | None = None,
    tolerancias_atributos: dict[str, float] | None = None,
) -> MatchResult:
    """Punto de entrada único: rankea, verifica, y arma el resultado auditable completo."""
    pesos = pesos or PesosMatching()
    umbrales = umbrales or UmbralesMatching()

    if not candidatos_listado:
        return MatchResult(
            id_ml=producto_ml.id_ml,
            query_usada=query_usada,
            categoria="SIN_MATCH_CONFIABLE",
            candidato_elegido=None,
            candidatos_rankeados=[],
            candidatos_evaluados=[],
            motivo=(
                "La búsqueda en Alibaba no devolvió ningún resultado para esta query -- no es evidencia de que "
                "el producto no exista, solo de que esta estrategia de búsqueda no lo encontró "
                "(ver orquestador_matching.py sobre estrategias de retrieval)."
            ),
        )

    atributos_ml = extraer_atributos_texto_libre(producto_ml.texto_para_matching())
    rankeados = rankear_candidatos(producto_ml, candidatos_listado, embedder_texto, embedder_imagen, top_k, pesos)
    evaluados, elegido = verificar_candidatos(
        producto_ml, atributos_ml, rankeados, abrir_ficha, embedder_texto, embedder_imagen,
        pesos, umbrales, tolerancias_atributos,
    )

    if elegido is not None:
        motivo = f"Candidato elegido: {elegido.url_alibaba}. {elegido.motivo}"
        categoria = elegido.categoria
    else:
        vetados = sum(1 for c in evaluados if c.veto is not None)
        motivo = (
            f"Se agotaron los {len(evaluados)} candidatos verificables del top_k sin encontrar un match confiable "
            f"({vetados} vetados por atributo esencial incompatible, el resto por debajo del umbral de match)."
        )
        categoria = "SIN_MATCH_CONFIABLE"

    return MatchResult(
        id_ml=producto_ml.id_ml,
        query_usada=query_usada,
        categoria=categoria,
        candidato_elegido=elegido,
        candidatos_rankeados=rankeados,
        candidatos_evaluados=evaluados,
        motivo=motivo,
    )


def match_result_a_dict(
    resultado: MatchResult, pesos: PesosMatching | None = None, umbrales: UmbralesMatching | None = None
) -> dict:
    """
    Convierte un `MatchResult` (y todos sus dataclasses anidados) a un
    dict JSON-serializable, listo para `db.insertar_resultado_matching`.
    Si se pasan `pesos`/`umbrales`, quedan registrados junto al resultado
    -- deja trazabilidad de con qué configuración se corrió esta vez
    (ajuste #5: todavía no son valores fijos).
    """
    data = asdict(resultado)
    data["pesos"] = asdict(pesos) if pesos is not None else None
    data["umbrales"] = asdict(umbrales) if umbrales is not None else None
    return data
