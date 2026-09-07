# comparator (pendiente)

Todavía no implementado. Queda para una sesión posterior, una vez que se
valide que `collector_alibaba/` extrae bien el catálogo completo del
proveedor.

Cuando se retome, este módulo va a tomar el catálogo persistido en
`database/` (fase 1: solo Alibaba; fase 2: con datos de Mercado Libre) y
calcular métricas de rentabilidad / score de ranking, en la línea de lo que
ya hace `alibaba-ml-comparador/calculos.py` para la carga manual.
