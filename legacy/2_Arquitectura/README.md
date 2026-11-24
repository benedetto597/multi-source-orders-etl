**Autor**: Edgar Benedetto  
**Fecha**: 2026-02-05  
**Fase**: 2 - Arquitectura  

---
# Fase 2 Arquitectura

## 📋 Descripción

El objetivo de esta fase es armar la arquitectura del pipeline de ETL que consolidará los datos históricos de las ordenes de compra de los dos centros de distribución en una sola tabla y eliminará duplicados manteniendo el registro más

---

## 📊 Análisis de Requisitos

### Fuentes de Datos

#### SQL Server (Datos Históricos)
- **Tablas**:
  - `ordenes_compra_ubicacion_1`: 31,116 registros (hasta 2025)
  - `ordenes_compra_ubicacion_2`: 31,124 registros (hasta 2024)
- **Total histórico**: 62,240 registros

#### CSVs Incrementales (Datos 2024)
- **Periodo**: Marzo - Diciembre 2024
- **Archivos**: 20 CSVs en total
  - 10 archivos de ubicacion_1
  - 10 archivos de ubicacion_2
- **Total**: 48,155 registros (aprox. 22,075 por ubicación)
- **Organización**: Separados en carpetas por ubicación

### Destino
- **Motor**: SQLite
- **Archivo**: `destino.db`
- **Tabla**: `ordenes_compra_consolidadas`

---

## 🎯 Objetivos del ETL

1. **Consolidar** datos de 2 centros de distribución en una sola tabla
2. **Eliminar duplicados** manteniendo el registro más reciente
3. **Identificar** cada centro de distribución en los datos finales
4. **Garantizar** integridad de datos (0 duplicados en destino)
5. **Normalizar** esquemas inconsistentes entre fuentes

---

## 🏗️ Arquitectura del Pipeline

### Diagrama de Flujo

```
┌────────────────────────────────────────────────────────────┐
│                        EXTRACT                             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │  SQL Server      │        │  CSVs (20 files) │          │
│  │  ─────────────   │        │  ──────────────  │          │
│  │  Ubicación 1     │        │  ubicacion_1/    │          │
│  │  31,116 regs     │        │    10 archivos   │          │
│  │                  │        │  ubicacion_2/    │          │
│  │  Ubicación 2     │        │    10 archivos   │          │
│  │  31,124 regs     │        │  48,155 regs     │          │
│  └────────┬─────────┘        └────────┬─────────┘          │
│           │                           │                    │
│           └───────────┬───────────────┘                    │
│                       ▼                                    │
│            ┌──────────────────────┐                        │
│            │  DataFrame Raw       │                        │
│            │  110,395 registros   │                        │
│            └──────────┬───────────┘                        │
└───────────────────────┼────────────────────────────────────┘
                        │
┌───────────────────────┼────────────────────────────────────┐
│                       ▼         TRANSFORM                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌────────────────────────────────────────────┐            │
│  │ 1. Normalizar Tipos de Datos               │            │
│  │    - id → TEXT                             │            │
│  │    - codigo_orden → TEXT                   │            │
│  │    - fechas → TIMESTAMP                    │            │
│  │    - cantidad_solicitada → INTEGER         │            │
│  └────────────────┬───────────────────────────┘            │
│                   ▼                                        │
│  ┌────────────────────────────────────────────┐            │
│  │ 2. Agregar Metadata                        │            │
│  │    - centro_distribucion                   │            │
│  │    - fuente (sql_ubicacion_X / csv)        │            │
│  │    - fecha_carga                           │            │
│  └────────────────┬───────────────────────────┘            │
│                   ▼                                        │
│  ┌────────────────────────────────────────────┐            │
│  │ 3. Parsear Fechas                          │            │
│  │    - pd.to_datetime() con errors='coerce'  │            │
│  └────────────────┬───────────────────────────┘            │
└───────────────────┼────────────────────────────────────────┘
                    │
┌───────────────────┼────────────────────────────────────────┐
│                   ▼        DEDUPLICATE                     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌────────────────────────────────────────────┐            │
│  │ Estrategia de Deduplicación:               │            │
│  │                                            │            │
│  │ 1. Agrupar por (id + centro_distribucion)  │            │
│  │ 2. Ordenar por fecha_actualizacion DESC    │            │
│  │ 3. Mantener primer registro (más reciente) │            │
│  │ 4. Fallback: usar fecha_ingreso si NULL    │            │
│  └────────────────┬───────────────────────────┘            │
│                   ▼                                        │
│  ┌──────────────────────────────┐                          │
│  │  DataFrame Limpio            │                          │
│  │  95,458 registros únicos     │                          │
│  │  (eliminados 14,937 dupl.)   │                          │
│  └────────────────┬─────────────┘                          │
└───────────────────┼────────────────────────────────────────┘
                    │
┌───────────────────┼────────────────────────────────────────┐
│                   ▼           LOAD                         │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌────────────────────────────────────────────┐            │
│  │ 1. Crear Tabla en SQLite                   │            │
│  │    - Ejecutar ESQUEMA_SQL                  │            │
│  │    - Crear índices                         │            │
│  └────────────────┬───────────────────────────┘            │
│                   ▼                                        │
│  ┌────────────────────────────────────────────┐            │
│  │ 2. Truncate (Full Refresh)                 │            │
│  │    - DELETE FROM tabla                     │            │
│  └────────────────┬───────────────────────────┘            │
│                   ▼                                        │
│  ┌────────────────────────────────────────────┐            │
│  │ 3. Insert Registros                        │            │
│  │    - df.to_sql(if_exists='append')         │            │
│  └────────────────┬───────────────────────────┘            │
│                   ▼                                        │
│  ┌──────────────────────────────┐                          │
│  │  destino.db                  │                          │
│  │  ordenes_compra_consolidadas │                          │
│  │  95,458 registros            │                          │
│  └────────────────┬─────────────┘                          │
└───────────────────┼────────────────────────────────────────┘
                    │
┌───────────────────┼────────────────────────────────────────┐
│                   ▼         VALIDATE                       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌───────────────────────────────────────────┐             │
│  │ Validaciones:                             │             │
│  │                                           │             │
│  │ ✓ Total registros = esperado              │             │
│  │ ✓ Duplicados = 0                          │             │
│  │ ✓ Centros = [ubicacion_1, ubicacion_2]    │             │
│  │ ✓ Estados = valores válidos               │             │
│  │ ✓ Rango fechas correcto                   │             │
│  └───────────────────────────────────────────┘             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Diseño de Clases (OOP)

### Principios Aplicados
- **SRP** (Single Responsibility Principle): Cada clase una responsabilidad
- **Separation of Concerns**: Extracción, transformación y carga separadas
- **DRY** (Don't Repeat Yourself): Funciones reutilizables

### Clases Principales

```python
SQLServerExtractor
├── __init__(config)
├── _build_connection_string()
├── extract_table(table_name, ubicacion)
└── extract_all_tables()

CSVExtractor
├── __init__(csv_directory)
└── extract_csvs()

DataTransformer
├── normalize_schema(df)
└── add_metadata(df)

Deduplicator
└── remove_duplicates(df)

SQLiteLoader
├── __init__(db_path)
├── create_table()
├── truncate_table()
├── load_data(df)
└── validate_load()
```

---

## 📐 Esquema Unificado

### Tabla: `ordenes_compra_consolidadas`

| Columna | Tipo | Descripción | Fuente Original |
|---------|------|-------------|-----------------|
| id | TEXT | Identificador único (PK) | Todas las fuentes |
| centro_distribucion | TEXT | ubicacion_1 / ubicacion_2 | **Nueva** |
| codigo_orden | TEXT | Código de orden | Todas las fuentes |
| codigo_producto | INTEGER | Código de producto | Todas las fuentes |
| estado | TEXT | Estado de la orden | Todas las fuentes |
| cantidad | INTEGER | Cantidad entregada | Todas las fuentes |
| cantidad_solicitada | INTEGER | Cantidad solicitada | Todas las fuentes |
| total | REAL | Monto total | Todas las fuentes |
| fecha_ingreso | TIMESTAMP | Fecha de creación | Todas las fuentes |
| fecha_actualizacion | TIMESTAMP | Fecha de última actualización | Todas las fuentes |
| codigo_proveedor | TEXT | Código de proveedor | Todas las fuentes |
| mes_act | TEXT | Mes de actualización | Solo CSVs |
| fuente | TEXT | Origen del dato | **Nueva** |
| fecha_carga | TIMESTAMP | Timestamp de carga ETL | **Nueva** |

### Índices

```sql
CREATE INDEX idx_centro ON ordenes_compra_consolidadas(centro_distribucion);
CREATE INDEX idx_fecha_ingreso ON ordenes_compra_consolidadas(fecha_ingreso);
CREATE INDEX idx_estado ON ordenes_compra_consolidadas(estado);
CREATE INDEX idx_codigo_orden ON ordenes_compra_consolidadas(codigo_orden);
```

---

## 🎯 Estrategia de Deduplicación

### Identificador Único
```
(id + centro_distribucion)
```

### Criterio de Resolución
1. Ordenar por `fecha_actualizacion DESC`
2. Si `fecha_actualizacion` es NULL, usar `fecha_ingreso DESC`
3. Mantener primer registro (más reciente)
4. Eliminar resto

### Ejemplo

**Antes (Duplicados):**
| id | centro | fecha_actualizacion |
|----|--------|---------------------|
| 123 | ubicacion_1 | 2024-05-15 |
| 123 | ubicacion_1 | 2024-06-20 | ← Mantener (más reciente)
| 123 | ubicacion_1 | 2024-04-10 |

**Después:**
| id | centro | fecha_actualizacion |
|----|--------|---------------------|
| 123 | ubicacion_1 | 2024-06-20 |

---

## ✅ Métricas de Validación

```python
VALIDACIONES = {
    'total_registros': 84629,
    'duplicados': 0,
    'centros': ['ubicacion_1', 'ubicacion_2'],
    'estados_validos': ['Cerrado', 'En proceso', 'Cancelado'],
    'rango_fechas': ('2023-01-02', '2024-12-31')
}
```

---

## 🔄 Manejo de Errores

### Logging
- Archivo: `etl_ordenes_compra.log`
- Niveles: INFO, WARNING, ERROR
- Formato: `timestamp - nivel - mensaje`

### Excepciones
- Try-catch en cada fase crítica
- Rollback implícito (full refresh)
- Exit code: 0 (éxito) / 1 (error)

---

## 🚀 Escalabilidad Futura

### Para Volúmenes Mayores
- Implementar procesamiento por batches
- Usar Pandas con chunks
- Considerar Dask para big data

### Para Ejecución Recurrente
- Cambiar de Full Refresh a Upsert
- Implementar CDC (Change Data Capture)
- Agregar columnas de control (is_deleted, version)

### Para Orquestación
- Migrar a Airflow DAG
- Implementar retry logic
- Agregar alertas (email, Slack)

---

## 📊 Decisiones de Diseño

### ¿Por qué Full Refresh en lugar de Incremental?

**Ventajas del Full Refresh:**
- ✅ Simplicidad de implementación
- ✅ Garantiza consistencia total
- ✅ No requiere tracking de cambios
- ✅ Adecuado para volumen actual (~86K registros)

**Cuándo cambiar a Incremental:**
- Cuando el volumen supere 1M registros
- Cuando el tiempo de ejecución sea crítico
- Cuando se requiera CDC