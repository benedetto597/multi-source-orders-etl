-- =========================================================================
-- @author: Edgar Benedetto
-- @fecha: 2026-02-07
-- @versión: 1.0
-- =========================================================================
-- QUERIES DE ANÁLISIS - ETL ÓRDENES DE COMPRA
-- =========================================================================
-- Queries útiles para analizar los datos cargados en destino.db
-- Ejecutar con: sqlite3 destino.db < queries_analisis.sql
-- O desde Python/DBeaver/DB Browser for SQLite
-- =========================================================================
-- NOTAS DE USO
-- =========================================================================
-- 
-- Para ejecutar desde línea de comandos:
--   sqlite3 destino.db < queries_analisis.sql
--
-- Para ejecutar query específico:
--   sqlite3 destino.db "SELECT COUNT(*) FROM ordenes_compra_consolidadas;"
--
-- Para exportar a CSV:
--   sqlite3 destino.db
--   .mode csv
--   .output reporte.csv
--   SELECT * FROM ordenes_compra_consolidadas;
--   .quit
--
-- =========================================================================
-- 1. OVERVIEW GENERAL
-- =========================================================================

-- Total de registros por centro y fuente
SELECT 
    centro_distribucion,
    fuente,
    COUNT(*) as total_registros,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM ordenes_compra_consolidadas), 2) as porcentaje
FROM ordenes_compra_consolidadas
GROUP BY centro_distribucion, fuente
ORDER BY centro_distribucion, fuente;

-- =========================================================================
-- 2. VERIFICACIÓN DE CALIDAD
-- =========================================================================

-- Verificar duplicados (debe retornar 0 filas)
SELECT 
    id, 
    centro_distribucion, 
    COUNT(*) as repeticiones
FROM ordenes_compra_consolidadas
GROUP BY id, centro_distribucion
HAVING COUNT(*) > 1;

-- Registros con valores nulos en campos críticos
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN id IS NULL THEN 1 ELSE 0 END) as id_nulo,
    SUM(CASE WHEN centro_distribucion IS NULL THEN 1 ELSE 0 END) as centro_nulo,
    SUM(CASE WHEN codigo_orden IS NULL THEN 1 ELSE 0 END) as codigo_orden_nulo,
    SUM(CASE WHEN estado IS NULL THEN 1 ELSE 0 END) as estado_nulo
FROM ordenes_compra_consolidadas;

-- =========================================================================
-- 3. ANÁLISIS POR ESTADO
-- =========================================================================

-- Distribución de órdenes por estado
SELECT 
    estado,
    COUNT(*) as total_ordenes,
    SUM(cantidad) as total_cantidad,
    SUM(total) as monto_total,
    ROUND(AVG(total), 2) as promedio_monto,
    MIN(total) as monto_min,
    MAX(total) as monto_max
FROM ordenes_compra_consolidadas
GROUP BY estado
ORDER BY total_ordenes DESC;

-- Órdenes por estado y centro de distribución
SELECT 
    centro_distribucion,
    estado,
    COUNT(*) as total_ordenes,
    SUM(total) as monto_total
FROM ordenes_compra_consolidadas
GROUP BY centro_distribucion, estado
ORDER BY centro_distribucion, estado;

-- =========================================================================
-- 4. ANÁLISIS TEMPORAL
-- =========================================================================

-- Órdenes por año y mes (fecha de ingreso)
SELECT 
    strftime('%Y', fecha_ingreso) as año,
    strftime('%m', fecha_ingreso) as mes,
    COUNT(*) as total_ordenes,
    SUM(total) as monto_total
FROM ordenes_compra_consolidadas
WHERE fecha_ingreso IS NOT NULL
GROUP BY año, mes
ORDER BY año, mes;

-- Órdenes por trimestre
SELECT 
    strftime('%Y', fecha_ingreso) as año,
    CASE 
        WHEN CAST(strftime('%m', fecha_ingreso) AS INTEGER) BETWEEN 1 AND 3 THEN 'Q1'
        WHEN CAST(strftime('%m', fecha_ingreso) AS INTEGER) BETWEEN 4 AND 6 THEN 'Q2'
        WHEN CAST(strftime('%m', fecha_ingreso) AS INTEGER) BETWEEN 7 AND 9 THEN 'Q3'
        ELSE 'Q4'
    END as trimestre,
    COUNT(*) as total_ordenes,
    SUM(total) as monto_total
FROM ordenes_compra_consolidadas
WHERE fecha_ingreso IS NOT NULL
GROUP BY año, trimestre
ORDER BY año, trimestre;

-- Tiempo promedio entre ingreso y actualización (en días)
SELECT 
    estado,
    ROUND(AVG(JULIANDAY(fecha_actualizacion) - JULIANDAY(fecha_ingreso)), 2) as dias_promedio,
    MIN(JULIANDAY(fecha_actualizacion) - JULIANDAY(fecha_ingreso)) as dias_min,
    MAX(JULIANDAY(fecha_actualizacion) - JULIANDAY(fecha_ingreso)) as dias_max
FROM ordenes_compra_consolidadas
WHERE fecha_actualizacion IS NOT NULL 
  AND fecha_ingreso IS NOT NULL
GROUP BY estado;

-- =========================================================================
-- 5. ANÁLISIS POR PROVEEDOR
-- =========================================================================

-- Top 10 proveedores por volumen de órdenes
SELECT 
    codigo_proveedor,
    COUNT(*) as total_ordenes,
    SUM(cantidad) as total_cantidad,
    SUM(total) as monto_total,
    ROUND(AVG(total), 2) as promedio_orden
FROM ordenes_compra_consolidadas
GROUP BY codigo_proveedor
ORDER BY total_ordenes DESC
LIMIT 10;

-- Proveedores por centro de distribución
SELECT 
    centro_distribucion,
    codigo_proveedor,
    COUNT(*) as total_ordenes,
    SUM(total) as monto_total
FROM ordenes_compra_consolidadas
GROUP BY centro_distribucion, codigo_proveedor
HAVING total_ordenes > 100
ORDER BY centro_distribucion, total_ordenes DESC;

-- =========================================================================
-- 6. ANÁLISIS DE PRODUCTOS
-- =========================================================================

-- Top 20 productos más solicitados
SELECT 
    codigo_producto,
    COUNT(*) as veces_ordenado,
    SUM(cantidad_solicitada) as total_solicitado,
    SUM(cantidad) as total_entregado,
    SUM(total) as monto_total
FROM ordenes_compra_consolidadas
GROUP BY codigo_producto
ORDER BY veces_ordenado DESC
LIMIT 20;

-- Productos con mayor diferencia entre solicitado y entregado
SELECT 
    codigo_producto,
    COUNT(*) as ordenes,
    SUM(cantidad_solicitada) as total_solicitado,
    SUM(cantidad) as total_entregado,
    SUM(cantidad_solicitada - cantidad) as diferencia,
    ROUND(100.0 * SUM(cantidad) / SUM(cantidad_solicitada), 2) as tasa_cumplimiento
FROM ordenes_compra_consolidadas
WHERE cantidad_solicitada > 0
GROUP BY codigo_producto
HAVING diferencia > 100
ORDER BY diferencia DESC
LIMIT 20;

-- =========================================================================
-- 7. MÉTRICAS DE NEGOCIO
-- =========================================================================

-- KPIs generales por centro
SELECT 
    centro_distribucion,
    COUNT(*) as total_ordenes,
    COUNT(DISTINCT codigo_producto) as productos_distintos,
    COUNT(DISTINCT codigo_proveedor) as proveedores_distintos,
    SUM(cantidad_solicitada) as cantidad_total_solicitada,
    SUM(cantidad) as cantidad_total_entregada,
    SUM(total) as monto_total,
    ROUND(AVG(total), 2) as ticket_promedio,
    ROUND(100.0 * SUM(cantidad) / SUM(cantidad_solicitada), 2) as tasa_cumplimiento
FROM ordenes_compra_consolidadas
WHERE cantidad_solicitada > 0
GROUP BY centro_distribucion;

-- Órdenes con total = 0 (posibles cancelaciones o devoluciones)
SELECT 
    estado,
    COUNT(*) as ordenes_sin_monto,
    SUM(cantidad) as cantidad_total
FROM ordenes_compra_consolidadas
WHERE total = 0
GROUP BY estado;

-- =========================================================================
-- 8. ANÁLISIS DE FUENTE DE DATOS
-- =========================================================================

-- Comparación entre datos históricos (SQL) e incrementales (CSV)
SELECT 
    fuente,
    COUNT(*) as total_registros,
    MIN(fecha_ingreso) as fecha_min,
    MAX(fecha_ingreso) as fecha_max,
    SUM(total) as monto_total
FROM ordenes_compra_consolidadas
GROUP BY fuente
ORDER BY fuente;

-- Registros por mes y fuente (para ver cobertura)
SELECT 
    strftime('%Y-%m', fecha_ingreso) as año_mes,
    fuente,
    COUNT(*) as total_registros
FROM ordenes_compra_consolidadas
WHERE fecha_ingreso IS NOT NULL
GROUP BY año_mes, fuente
ORDER BY año_mes, fuente;

-- =========================================================================
-- 9. DETECCIÓN DE ANOMALÍAS
-- =========================================================================

-- Órdenes con cantidades sospechosas (muy altas)
SELECT 
    id,
    centro_distribucion,
    codigo_producto,
    cantidad,
    cantidad_solicitada,
    total,
    estado
FROM ordenes_compra_consolidadas
WHERE cantidad > 10000 OR cantidad_solicitada > 10000
ORDER BY cantidad DESC
LIMIT 20;

-- Órdenes con montos muy altos
SELECT 
    id,
    centro_distribucion,
    codigo_producto,
    cantidad,
    total,
    estado,
    codigo_proveedor
FROM ordenes_compra_consolidadas
WHERE total > 100000
ORDER BY total DESC
LIMIT 20;

-- Órdenes con cantidad entregada > cantidad solicitada
SELECT 
    id,
    centro_distribucion,
    codigo_producto,
    cantidad_solicitada,
    cantidad,
    (cantidad - cantidad_solicitada) as exceso,
    estado
FROM ordenes_compra_consolidadas
WHERE cantidad > cantidad_solicitada
ORDER BY exceso DESC
LIMIT 20;

-- =========================================================================
-- 10. EXPORTACIÓN DE DATOS
-- =========================================================================

-- Vista completa para exportación a Excel/CSV
-- (Usar con .mode csv y .output archivo.csv en sqlite3)
SELECT 
    id,
    centro_distribucion,
    codigo_orden,
    codigo_producto,
    estado,
    cantidad,
    cantidad_solicitada,
    total,
    fecha_ingreso,
    fecha_actualizacion,
    codigo_proveedor,
    fuente,
    fecha_carga
FROM ordenes_compra_consolidadas
ORDER BY fecha_ingreso DESC;