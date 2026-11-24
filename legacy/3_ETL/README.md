**Autor**: Edgar Benedetto  
**Fecha**: 2026-02-07  
**Fase**: 3 - ETL    

---
# ETL - Consolidación de Órdenes de Compra

## 📋 Descripción

Pipeline ETL que consolida órdenes de compra de 2 centros de distribución desde múltiples fuentes:
- **SQL Server**: Datos históricos hasta 2025
- **CSVs**: Datos incrementales 2024

Elimina duplicados y carga en SQLite con esquema unificado.

---

## 📁 Estructura de Archivos

```
proyecto/
├── csvs/                       # Carpeta con CSVs organizados por ubicación
│   ├── ubicacion_1/            # CSVs de ubicación 1
│   │   ├── ordenes_202403.csv
│   │   ├── ordenes_202404.csv
│   │   └── ...
│   └── ubicacion_2/            # CSVs de ubicación 2
│       ├── ordenes_202403.csv
│       ├── ordenes_202404.csv
│       └── ...
├── logs/
│    └── etl_ordenes_compra.log  # Log de ejecución (generado)
├── 03_etl.py                    # Script principal
├── etl_metadata.json            # Configuración de metadata de ETL (generado)
└── README.md

```

---

## 🚀 Uso

### Primera Ejecución
La primera ejecución debe ser en el modo Full Refresh (v1.0). En este caso, se extraen todos los registros de las tablas de SQL Server y CSVs, normalizando los datos y eliminando duplicados. El resultado se almacena en SQLite.

### Ejecución Incremental (Opcional)
La ejecución en el modo Incremental (v2.0). En este caso, se extraen únicamente los últimos x meses de registros de las tablas de SQL Server y CSVs.

### Ejecución
```bash
py 03_etl.py
```

## 📊 Cuándo Usar Cada Modo

### Full Refresh (`enabled: False`)
✅ Primera carga  
✅ Tabla pequeña (< 100K)  
✅ Datos cambian impredeciblemente  
✅ Necesitas "empezar de cero"

### Incremental (`enabled: True`)
✅ Ejecuciones frecuentes (diario/semanal)  
✅ Tabla grande (> 100K)  
✅ Solo datos recientes cambian  
✅ Quieres optimizar performance  
✅ Necesitas preservar historia

---

## ⚙️ Configuración de la version 2.0 del ETL

### Activar/Desactivar Modo Incremental

En `03_etl.py`, está configuración para la activación o desactivación del modo incremental.

```python
INCREMENTAL_CONFIG = {
    'enabled': True,  # ⬅️ Cambiar a False para full refresh
    'lookback_months': 12,  # Ventana de meses
    'date_column': 'fecha_actualizacion',
    'fallback_column': 'fecha_ingreso',
    'use_upsert': True  # ⬅️ True=UPSERT, False=TRUNCATE+INSERT
}
```

**Comportamiento incremental**: Optimizado
- Extrae solo últimos 12 meses
- UPSERT (UPDATE + INSERT)
- Guarda metadata en JSON

### Modo Full Refresh (Default)

```python
INCREMENTAL_CONFIG = {
    'enabled': False,  # ⬅️ Desactivar incremental
    ...
}
```

---

## 📈 Arquitectura

### Modo Full Refresh (v1.0)
```
EXTRACT: 110,395 registros (todo)
TRANSFORM: Normalización
DEDUPLICATE: -14,937 duplicados
LOAD: TRUNCATE + INSERT → 95,458 registros
```

### Modo Incremental (v2.0)
```
EXTRACT: ~48,000 registros (últimos 12 meses)
TRANSFORM: Normalización
DEDUPLICATE: -X duplicados
LOAD: UPSERT → Inserts + Updates
METADATA: Guardar watermark
```

---

## ✅ Ventajas del Modo Incremental

### 1. **Performance**
- 60% más rápido
- Tiempo constante (no crece)

### 2. **Seguridad**
- No hay TRUNCATE (nunca pierdes datos)
- Falla segura (UPSERT atómico)

### 3. **Auditoría**
- `fecha_modificacion`: saber cuándo se actualizó cada registro
- Metadata JSON: tracking de ejecuciones

### 4. **Flexibilidad**
- Ajustar ventana según necesidad (6, 12, 24 meses)
- Volver a full refresh con 1 línea

---


## 🎯 Estrategia de Deduplicación

1. **Identificador único**: `id` + `centro_distribucion`
2. **Criterio de resolución**: Registro con `fecha_actualizacion` más reciente
3. **Fallback**: Si `fecha_actualizacion` es NULL, usa `fecha_ingreso`
4. **Tracking**: Métricas de duplicados en log

---

## 📊 Arquitectura

```
EXTRACT
├── SQL Server Ubicación 1 → 31,116 registros
├── SQL Server Ubicación 2 → 31,124 registros
└── CSVs (10 archivos)    → 48,155 registros
                            ─────────────────
                            Total: 110,395 registros
TRANSFORM
├── Normalizar tipos de datos
├── Parsear fechas
├── Agregar metadata (centro, fuente)
└── Identificar centros por codigo_orden

DEDUPLICATE
├── Criterio: id + centro_distribucion
└── Mantener más reciente → Elimina 14,937 registros duplicados

LOAD
└── SQLite → 95,458 registros únicos
```

---

## ⚙️ Customización

### Cambiar Estrategia de Deduplicación

En clase `Deduplicator`, método `remove_duplicates()`:

```python
# Ejemplo: Mantener el registro con mayor total
df_sorted = df.sort_values(
    by=['id', 'centro_distribucion', 'total'],
    ascending=[True, True, False]  # Mayor total primero
)
```

### Agregar Validaciones Adicionales

En clase `SQLiteLoader`, método `validate_load()`:

```python
# Ejemplo: Validar rangos de fechas
rango_fechas = pd.read_sql(
    f"SELECT MIN(fecha_ingreso), MAX(fecha_ingreso) FROM {TABLA_DESTINO}",
    conn
)
```

---

## 📝 Logs

El archivo `etl_ordenes_compra.log` contiene:
- Timestamp de cada operación
- Conteos de registros por fase
- Métricas de deduplicación
- Errores detallados (si ocurren)

---

## 🐛 Troubleshooting

### Error: "ODBC Driver not found"
→ Instalar ODBC Driver 18 for SQL Server

### Error: "No such file or directory: csvs_incrementales"
→ Crear carpeta y mover CSVs ahí, o ajustar `CSV_DIRECTORY`

### Error: "Authentication failed"
→ Verificar credenciales en `SQL_SERVER_CONFIG`

### Warning: "No se encontraron CSVs"
→ Verificar que los archivos CSV estén en `CSV_DIRECTORY`

---


## 🎓 Notas de Diseño

### Por qué esta arquitectura:

1. **Clases modulares**: Cada componente tiene responsabilidad única (SRP)
2. **Logging exhaustivo**: Permite debugging y auditoría
3. **Esquema fuertemente tipado**: Previene errores de datos
4. **Deduplicación inteligente**: Basada en lógica de negocio (fecha más reciente)
5. **Validaciones post-carga**: Garantiza integridad
6. **Metadata tracking**: `fuente` y `fecha_carga` para lineage
7. **Full refresh**: Truncate + Insert para simplicidad (escalable a upsert si se requiere)
8. **Incremental**: UPSERT para optimización de performance

### Escalabilidad:

- Para volúmenes mayores: Cambiar a batch processing
- Para frecuencia alta: Implementar CDC (Change Data Capture)
- Para distributed: Migrar a Spark/Airflow
