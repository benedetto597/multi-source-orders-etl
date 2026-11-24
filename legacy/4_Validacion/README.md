**Autor**: Edgar Benedetto  
**Fecha**: 2026-02-07  
**Fase**: 4 - Validacion    

---
# Fase 4: Validación de Datos

## 📋 Descripción

Scripts y queries para validar la calidad e integridad de los datos cargados en `destino.db` después de ejecutar el ETL.

---

## 📁 Archivos

```
4_Validacion/
├── analisis/
│    └── queries_analisis.sql                       # queries de análisis
├── reportes/
│    ├── reporte_validacion_20260207_162614.txt     # reporte de validación (generado)
│    ├── reporte_validacion_20260207_164836.txt     
│    ├── reporte_validacion_20260207_164841.txt     
│    └── ...
├── 04_validacion.py                                # Script principal de validación
└── README.md
```

---

## 🚀 Uso Rápido

Este script ejecuta automáticamente **8 validaciones críticas**:

1. ✓ Existencia de tabla
2. ✓ Conteo de registros (rango esperado)
3. ✓ Duplicados (debe ser 0)
4. ✓ Valores nulos en campos críticos
5. ✓ Centros de distribución válidos
6. ✓ Estados válidos
7. ✓ Rangos de fechas
8. ✓ Consistencia de datos numéricos

---

## ⚙️ Personalización del Validador

### Ajustar Métricas Esperadas

En `04_validacion.py`, líneas 18-26:

```python
METRICAS_ESPERADAS = {
    'total_registros_min': 84000,  # Ajustar según los nuevos datos
    'total_registros_max': 87000,  
    'duplicados': 0,
    'centros': ['ubicacion_1', 'ubicacion_2'],
    'estados_validos': ['Cerrado', 'En proceso', 'Cancelado'],
    'fuentes_validas': ['sql_ubicacion_1', 'sql_ubicacion_2', 'csv'],
    'fecha_min': '2023-01-01',
    'fecha_max': '2025-12-31'
}
```

### Agregar Nuevas Validaciones

Agrega métodos a la clase `DataValidator`:

```python
def validar_nueva_regla(self) -> bool:
    """Valida nueva regla personalizada"""
    print("\n[9] Validando nueva regla...")
    
    try:
        with self.conectar() as conn:
            # Query
            query = "SELECT ..."
            resultado = pd.read_sql(query, conn)
            
            # Lógica de validación
            if condicion:
                self.agregar_resultado("Nueva Regla", "[OK] PASS", "OK")
                return True
            else:
                self.agregar_resultado("Nueva Regla", "[FAIL] FAIL", "Problema")
                return False
                
    except Exception as e:
        self.agregar_resultado("Nueva Regla", "[FAIL] ERROR", str(e))
        return False
```

Luego agrégala a `ejecutar_todas()`:

```python
def ejecutar_todas(self) -> bool:
    ...
    self.validar_consistencia_datos()
    self.validar_nueva_regla()  # ← Agregar aquí
    ...
```

---

## 🎯 Casos de Uso

### Validación Post-ETL (Automática)

Agrega al final de tu ETL:

```python
# En 03_etl.py, al final de main()
if exito: 
  logger.info("Ejecutando validaciones...") 
  result = subprocess.run( ['python', '04_validacion.py'], 
  cwd=os.path.join(os.path.dirname(__file__), '..', '4_Validacion'), 
  check=True ) 
logger.info(f"Validación finalizada con código {result.returncode}")
if result.returncode != 0:
  logger.warning("Algunas validaciones fallaron")
```

### Validación Manual

```bash
cd 4_Validacion
py validar_resultados.py
```

Revisar el reporte generado y confirmar que todo pasó.

### Análisis Exploratorio

```bash
# Conectar a la base de datos
sqlite3 ../3_ETL/destino.db

# Ejecutar queries interactivamente
sqlite> .mode column
sqlite> .headers on
sqlite> SELECT estado, COUNT(*) FROM ordenes_compra_consolidadas GROUP BY estado;
```

---

## 📈 Interpretación de Resultados

### ✓ PASS (Verde)
Todo correcto. La validación pasó exitosamente.

### ⚠ WARNING (Amarillo)
Advertencia. No es crítico pero debe revisarse.
- Ejemplo: Estados no esperados (puede ser legítimo)
- Ejemplo: Cantidades mayores a las solicitadas (puede ocurrir)

### ✗ FAIL (Rojo)
Error crítico. Debe corregirse antes de continuar.
- Ejemplo: Duplicados encontrados
- Ejemplo: Valores nulos en campos obligatorios

### ✗ ERROR (Rojo)
Error de ejecución. Problema técnico.
- Ejemplo: Tabla no existe
- Ejemplo: Query SQL inválido

---

## 🔧 Troubleshooting

### Error: "unable to open database file"
→ Verifica que `destino.db` existe en `../5_DestinoDB/`
→ Ajusta la ruta en línea 13 de `04_validacion.py`

### Error: "no such table: ordenes_compra_consolidadas"
→ El ETL no se ejecutó correctamente
→ Ejecuta primero `03_etl.py`

### Advertencias sobre estados/centros
→ Revisa si los valores son legítimos
→ Actualiza `METRICAS_ESPERADAS` si son válidos

---

## 📊 Métricas de Calidad Objetivo

| Métrica | Objetivo | Crítico |
|---------|----------|---------|
| Duplicados | 0 | ✓ |
| Valores nulos (id, centro, fuente) | 0 | ✓ |
| Registros totales | 84,000 - 100,000 | ✓ |
| Centros válidos | ubicacion_1, ubicacion_2 | ✓ |
| Estados válidos | Cerrado, En proceso, Cancelado | - |
| Cantidades negativas | 0 | ✓ |
| Rango de fechas | 2023-2025 | - |

