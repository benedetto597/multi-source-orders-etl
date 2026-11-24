"""
Fase 2 - Arquitectura
=====================================
Definición del esquema destino para ordenes_compra_consolidadas

Autor: Edgar Benedetto
Fecha: 2026-02-05
Versión: 1.0
"""

# =============================================================================
# ESQUEMA SQL LITE - TABLA DESTINO
# =============================================================================

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS ordenes_compra_consolidadas (
    -- Identificadores
    id TEXT NOT NULL,
    centro_distribucion TEXT NOT NULL,
    codigo_orden TEXT,
    codigo_producto INTEGER,
    PRIMARY KEY (id, centro_distribucion),
    
    -- Información de la orden
    estado TEXT,
    cantidad INTEGER,
    cantidad_solicitada INTEGER,
    total REAL,
    
    -- Fechas
    fecha_ingreso TIMESTAMP,
    fecha_actualizacion TIMESTAMP,
    
    -- Referencias
    codigo_proveedor TEXT,
    mes_act TEXT,
    
    -- Metadata (auditoría)
    fuente TEXT,
    fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# =============================================================================
# ÍNDICES PARA OPTIMIZACIÓN
# =============================================================================

INDICES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_centro ON ordenes_compra_consolidadas(centro_distribucion);",
    "CREATE INDEX IF NOT EXISTS idx_fecha_ingreso ON ordenes_compra_consolidadas(fecha_ingreso);",
    "CREATE INDEX IF NOT EXISTS idx_estado ON ordenes_compra_consolidadas(estado);",
    "CREATE INDEX IF NOT EXISTS idx_codigo_orden ON ordenes_compra_consolidadas(codigo_orden);",
]

# =============================================================================
# MAPEO DE TIPOS DE DATOS
# =============================================================================

TRANSFORMACIONES_TIPOS = {
    'id': {
        'sql_ubicacion_1': 'bigint',
        'sql_ubicacion_2': 'varchar(24)',
        'csv': 'int64',
        'destino': 'TEXT',
        'transformacion': 'Convertir todo a string'
    },
    'codigo_orden': {
        'sql_ubicacion_1': 'varchar(64)',
        'sql_ubicacion_2': 'int',
        'csv': 'float64',
        'destino': 'TEXT',
        'transformacion': 'Convertir a string, manejar NaN'
    },
    'codigo_producto': {
        'sql_ubicacion_1': 'float',
        'sql_ubicacion_2': 'int',
        'csv': 'float64',
        'destino': 'INTEGER',
        'transformacion': 'Convertir a int, rellenar 0 si NaN'
    },
    'cantidad_solicitada': {
        'sql_ubicacion_1': 'varchar(32)',
        'sql_ubicacion_2': 'bigint',
        'csv': 'int64',
        'destino': 'INTEGER',
        'transformacion': 'Parse string a int si es necesario'
    },
    'fecha_ingreso': {
        'sql_ubicacion_1': 'varchar(64)',
        'sql_ubicacion_2': 'datetime2',
        'csv': 'object',
        'destino': 'TIMESTAMP',
        'transformacion': 'pd.to_datetime() con errors=coerce'
    },
    'fecha_actualizacion': {
        'sql_ubicacion_1': 'datetime2',
        'sql_ubicacion_2': 'datetime2',
        'csv': 'object',
        'destino': 'TIMESTAMP',
        'transformacion': 'pd.to_datetime() con errors=coerce'
    }
}

# =============================================================================
# LÓGICA DE IDENTIFICACIÓN DE CENTRO DE DISTRIBUCIÓN
# =============================================================================

IDENTIFICACION_CENTRO = {
    'sql_server': {
        'ubicacion_1': "Tabla: ordenes_compra_ubicacion_1",
        'ubicacion_2': "Tabla: ordenes_compra_ubicacion_2"
    },
    'csv': {
        'ubicacion_1': "codigo_orden empieza con '1' (ej: 110012913)",
        'ubicacion_2': "codigo_orden empieza con '2' (ej: 210008248)"
    }
}

# =============================================================================
# ESTRATEGIA DE DEDUPLICACIÓN
# =============================================================================

ESTRATEGIA_DEDUPLICACION = {
    'identificador_unico': ['id', 'centro_distribucion'],
    'criterio_resolucion': 'fecha_actualizacion DESC (más reciente)',
    'fallback': 'Si fecha_actualizacion es NULL, usar fecha_ingreso',
    'accion': 'Mantener primer registro (más reciente), eliminar resto'
}

# =============================================================================
# MÉTRICAS DE VALIDACIÓN
# =============================================================================

METRICAS_ESPERADAS = {
    'registros_sql_ubicacion_1': 31116,
    'registros_sql_ubicacion_2': 31124,
    'registros_csv_total': 48155,
    'archivos_csv': 20,  # 10 por ubicación
    'total_extraido': 110395,
    'duplicados_estimados': 14937,
    'total_final_esperado': 95458,
    'duplicados_destino': 0
}

# =============================================================================
# COLUMNAS AGREGADAS (METADATA)
# =============================================================================

COLUMNAS_NUEVAS = {
    'centro_distribucion': {
        'descripcion': 'Identificador del centro de distribución',
        'valores': ['ubicacion_1', 'ubicacion_2'],
        'tipo': 'TEXT NOT NULL'
    },
    'fuente': {
        'descripcion': 'Origen de los datos',
        'valores': ['sql_ubicacion_1', 'sql_ubicacion_2', 'csv'],
        'tipo': 'TEXT'
    },
    'fecha_carga': {
        'descripcion': 'Timestamp de cuando se cargó el registro',
        'tipo': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
    }
}

# =============================================================================
# VALIDACIONES DE INTEGRIDAD
# =============================================================================

VALIDACIONES = [
    "Verificar 0 duplicados por (id + centro_distribucion)",
    "Verificar que centro_distribucion solo tenga valores: ubicacion_1, ubicacion_2",
    "Verificar que estado esté en: Cerrado, En proceso, Cancelado",
    "Verificar que fechas estén en rango: 2023-01-02 a 2024-12-31",
    "Verificar que total registros = SQL Server + CSV - duplicados"
]

if __name__ == "__main__":
    print("="*70)
    print("ESQUEMA DE DATOS - TABLA CONSOLIDADA".center(70))
    print("="*70)
    
    print("\n TABLA DESTINO:")
    print(ESQUEMA_SQL)
    
    print("\n ÍNDICES:")
    for idx in INDICES_SQL:
        print(f"  - {idx}")
    
    print("\n TRANSFORMACIONES DE TIPOS:")
    for campo, info in TRANSFORMACIONES_TIPOS.items():
        print(f"\n  {campo}:")
        print(f"    - Destino: {info['destino']}")
        print(f"    - Transformación: {info['transformacion']}")
    
    print("\n IDENTIFICACIÓN DE CENTROS:")
    print(f"  CSV Ubicación 1: {IDENTIFICACION_CENTRO['csv']['ubicacion_1']}")
    print(f"  CSV Ubicación 2: {IDENTIFICACION_CENTRO['csv']['ubicacion_2']}")
    
    print("\n ESTRATEGIA DE DEDUPLICACIÓN:")
    print(f"  - ID único: {ESTRATEGIA_DEDUPLICACION['identificador_unico']}")
    print(f"  - Criterio: {ESTRATEGIA_DEDUPLICACION['criterio_resolucion']}")
    
    print("\n MÉTRICAS ESPERADAS:")
    for metrica, valor in METRICAS_ESPERADAS.items():
        print(f"  - {metrica}: {valor:,}")
