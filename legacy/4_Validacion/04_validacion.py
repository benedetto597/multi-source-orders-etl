"""
Fase: 4 - Validación
=============================================
Valida la integridad y calidad de los datos cargados en destino.db

Autor: Edgar Benedetto
Fecha: 2026-02-07
Versión: 1.0
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
import sys

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Crear carpetas para reportes si no existen 
os.makedirs("reportes", exist_ok=True) 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB = os.path.join(BASE_DIR, "..", "5_DestinoBD", "destino.db")
TABLA = 'ordenes_compra_consolidadas'

# Valores esperados
METRICAS_ESPERADAS = {
    'total_registros_min': 84000,  # Mínimo esperado después de deduplicación
    'total_registros_max': 100000,  # Ajustado: Máximo posible
    'duplicados': 0,
    'centros': ['ubicacion_1', 'ubicacion_2'],
    'estados_validos': ['Cerrado', 'En proceso', 'Cancelado', 'Confirmado', 'Enviado', 'Facturado', 'Recibido Parcial'],
    'fuentes_validas': ['sql_ubicacion_1', 'sql_ubicacion_2', 'csv'],
    'fecha_min': '2023-01-01',
    'fecha_max': '2025-12-31'
}


# =============================================================================
# CLASE: VALIDADOR
# =============================================================================

class DataValidator:
    """Valida calidad e integridad de datos en SQLite"""
    
    def __init__(self, db_path: str, tabla: str):
        self.db_path = db_path
        self.tabla = tabla
        self.resultados = []
        self.errores = []
    
    def conectar(self):
        """Establece conexión a SQLite"""
        return sqlite3.connect(self.db_path)
    
    def agregar_resultado(self, nombre: str, resultado: str, detalle: str = ""):
        """Agrega resultado de validación"""
        self.resultados.append({
            'validacion': nombre,
            'resultado': resultado,
            'detalle': detalle
        })
    
    def agregar_error(self, mensaje: str):
        """Agrega error crítico"""
        self.errores.append(mensaje)
    
    # =========================================================================
    # VALIDACIONES BÁSICAS
    # =========================================================================
    
    def validar_tabla_existe(self) -> bool:
        """Valida que la tabla destino existe"""
        print("\n[1] Validando existencia de tabla...")
        
        try:
            with self.conectar() as conn:
                query = f"""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' AND name='{self.tabla}'
                """
                resultado = pd.read_sql(query, conn)
                
                if len(resultado) > 0:
                    self.agregar_resultado(
                        "Tabla existe", 
                        "[OK] PASS", 
                        f"Tabla '{self.tabla}' encontrada"
                    )
                    print(f"  [OK] Tabla '{self.tabla}' existe")
                    return True
                else:
                    self.agregar_resultado(
                        "Tabla existe", 
                        "[FAIL] FAIL", 
                        f"Tabla '{self.tabla}' NO encontrada"
                    )
                    self.agregar_error(f"Tabla '{self.tabla}' no existe")
                    print(f"  [ERROR] ERROR: Tabla '{self.tabla}' no existe")
                    return False
                    
        except Exception as e:
            self.agregar_resultado("Tabla existe", "[ERROR] ERROR", str(e))
            self.agregar_error(f"Error verificando tabla: {e}")
            print(f"  [ERROR] ERROR: {e}")
            return False
    
    def validar_conteo_registros(self) -> Dict:
        """Valida cantidad total de registros"""
        print("\n[2] Validando conteo de registros...")
        
        try:
            with self.conectar() as conn:
                # Conteo total
                total = pd.read_sql(
                    f"SELECT COUNT(*) as total FROM {self.tabla}", 
                    conn
                )['total'].values[0]
                
                print(f"  Total registros: {total:,}")
                
                # Validar rango esperado
                if METRICAS_ESPERADAS['total_registros_min'] <= total <= METRICAS_ESPERADAS['total_registros_max']:
                    self.agregar_resultado(
                        "Conteo total", 
                        "[OK] PASS", 
                        f"{total:,} registros (dentro del rango esperado)"
                    )
                    print(f"  [OK] Dentro del rango esperado")
                else:
                    self.agregar_resultado(
                        "Conteo total", 
                        "[!] WARNING", 
                        f"{total:,} registros (fuera del rango {METRICAS_ESPERADAS['total_registros_min']:,} - {METRICAS_ESPERADAS['total_registros_max']:,})"
                    )
                    print(f"  [!] ADVERTENCIA: Fuera del rango esperado")
                
                # Por centro
                por_centro = pd.read_sql(
                    f"SELECT centro_distribucion, COUNT(*) as total FROM {self.tabla} GROUP BY centro_distribucion",
                    conn
                )
                
                print(f"\n  Distribución por centro:")
                for _, row in por_centro.iterrows():
                    print(f"    - {row['centro_distribucion']}: {row['total']:,} registros")
                
                # Por fuente
                por_fuente = pd.read_sql(
                    f"SELECT fuente, COUNT(*) as total FROM {self.tabla} GROUP BY fuente",
                    conn
                )
                
                print(f"\n  Distribución por fuente:")
                for _, row in por_fuente.iterrows():
                    print(f"    - {row['fuente']}: {row['total']:,} registros")
                
                return {
                    'total': total,
                    'por_centro': por_centro.to_dict('records'),
                    'por_fuente': por_fuente.to_dict('records')
                }
                
        except Exception as e:
            self.agregar_resultado("Conteo total", "[ERROR] ERROR", str(e))
            self.agregar_error(f"Error en conteo: {e}")
            print(f"  [ERROR] ERROR: {e}")
            return {}
    
    def validar_duplicados(self) -> int:
        """Valida que no existan duplicados por (id + centro)"""
        print("\n[3] Validando duplicados...")
        
        try:
            with self.conectar() as conn:
                query = f"""
                SELECT COUNT(*) as duplicados 
                FROM (
                    SELECT id, centro_distribucion, COUNT(*) as cnt
                    FROM {self.tabla}
                    GROUP BY id, centro_distribucion
                    HAVING COUNT(*) > 1
                )
                """
                duplicados = pd.read_sql(query, conn)['duplicados'].values[0]
                
                if duplicados == 0:
                    self.agregar_resultado(
                        "Duplicados", 
                        "[OK] PASS", 
                        "0 duplicados encontrados"
                    )
                    print(f"  [OK] 0 duplicados (EXCELENTE)")
                else:
                    self.agregar_resultado(
                        "Duplicados", 
                        "[FAIL] FAIL", 
                        f"{duplicados} grupos duplicados encontrados"
                    )
                    self.agregar_error(f"Se encontraron {duplicados} duplicados")
                    print(f"  [ERROR] ERROR: {duplicados} duplicados encontrados")
                    
                    # Mostrar ejemplos de duplicados
                    ejemplos = pd.read_sql(f"""
                        SELECT id, centro_distribucion, COUNT(*) as repeticiones
                        FROM {self.tabla}
                        GROUP BY id, centro_distribucion
                        HAVING COUNT(*) > 1
                        LIMIT 5
                    """, conn)
                    print("\n  Ejemplos de duplicados:")
                    print(ejemplos.to_string(index=False))
                
                return duplicados
                
        except Exception as e:
            self.agregar_resultado("Duplicados", "[ERROR] ERROR", str(e))
            self.agregar_error(f"Error validando duplicados: {e}")
            print(f"  [ERROR] ERROR: {e}")
            return -1
    
    # =========================================================================
    # VALIDACIONES DE INTEGRIDAD
    # =========================================================================
    
    def validar_valores_nulos(self) -> Dict:
        """Valida valores nulos en campos críticos"""
        print("\n[4] Validando valores nulos...")
        
        campos_criticos = ['id', 'centro_distribucion', 'fuente']
        
        try:
            with self.conectar() as conn:
                resultados_nulos = {}
                
                for campo in campos_criticos:
                    query = f"SELECT COUNT(*) as nulos FROM {self.tabla} WHERE {campo} IS NULL"
                    nulos = pd.read_sql(query, conn)['nulos'].values[0]
                    resultados_nulos[campo] = nulos
                    
                    if nulos == 0:
                        print(f"  [OK] {campo}: 0 nulos")
                    else:
                        print(f"  [FAIL] {campo}: {nulos} nulos (NO DEBERÍA HABER)")
                        self.agregar_error(f"Campo '{campo}' tiene {nulos} valores nulos")
                
                todos_cero = all(v == 0 for v in resultados_nulos.values())
                
                if todos_cero:
                    self.agregar_resultado(
                        "Valores nulos críticos", 
                        "[OK] PASS", 
                        "Sin valores nulos en campos críticos"
                    )
                else:
                    self.agregar_resultado(
                        "Valores nulos críticos", 
                        "[FAIL] FAIL", 
                        f"Campos con nulos: {resultados_nulos}"
                    )
                
                return resultados_nulos
                
        except Exception as e:
            self.agregar_resultado("Valores nulos", "[ERROR] ERROR", str(e))
            print(f"  [ERROR] ERROR: {e}")
            return {}
    
    def validar_centros_distribucion(self) -> bool:
        """Valida que solo existan los centros esperados"""
        print("\n[5] Validando centros de distribución...")
        
        try:
            with self.conectar() as conn:
                query = f"SELECT DISTINCT centro_distribucion FROM {self.tabla}"
                centros = pd.read_sql(query, conn)['centro_distribucion'].tolist()
                
                centros_esperados = set(METRICAS_ESPERADAS['centros'])
                centros_encontrados = set(centros)
                
                print(f"  Centros encontrados: {centros}")
                
                if centros_encontrados == centros_esperados:
                    self.agregar_resultado(
                        "Centros válidos", 
                        "[OK] PASS", 
                        f"Centros correctos: {centros}"
                    )
                    print(f"  [OK] Centros correctos")
                    return True
                else:
                    extras = centros_encontrados - centros_esperados
                    faltantes = centros_esperados - centros_encontrados
                    
                    detalle = []
                    if extras:
                        detalle.append(f"Centros no esperados: {extras}")
                        print(f"  [FAIL] Centros no esperados: {extras}")
                    if faltantes:
                        detalle.append(f"Centros faltantes: {faltantes}")
                        print(f"  [FAIL] Centros faltantes: {faltantes}")
                    
                    self.agregar_resultado(
                        "Centros válidos", 
                        "[FAIL] FAIL", 
                        "; ".join(detalle)
                    )
                    self.agregar_error(f"Centros inválidos: {centros}")
                    return False
                    
        except Exception as e:
            self.agregar_resultado("Centros válidos", "[ERROR] ERROR", str(e))
            print(f"  [ERROR] ERROR: {e}")
            return False
    
    def validar_estados(self) -> bool:
        """Valida que los estados sean válidos"""
        print("\n[6] Validando estados...")
        
        try:
            with self.conectar() as conn:
                query = f"SELECT DISTINCT estado, COUNT(*) as total FROM {self.tabla} GROUP BY estado"
                estados = pd.read_sql(query, conn)
                
                print(f"\n  Estados encontrados:")
                for _, row in estados.iterrows():
                    print(f"    - {row['estado']}: {row['total']:,} registros")
                
                estados_encontrados = set(estados['estado'].tolist())
                estados_esperados = set(METRICAS_ESPERADAS['estados_validos'])
                
                estados_invalidos = estados_encontrados - estados_esperados
                
                if len(estados_invalidos) == 0:
                    self.agregar_resultado(
                        "Estados válidos", 
                        "[OK] PASS", 
                        f"Todos los estados son válidos"
                    )
                    print(f"\n  [OK] Todos los estados son válidos")
                    return True
                else:
                    self.agregar_resultado(
                        "Estados válidos", 
                        "[!] WARNING", 
                        f"Estados no esperados: {estados_invalidos}"
                    )
                    print(f"\n  [!] Estados no esperados: {estados_invalidos}")
                    return False
                    
        except Exception as e:
            self.agregar_resultado("Estados válidos", "[ERROR] ERROR", str(e))
            print(f"  [ERROR] ERROR: {e}")
            return False
    
    def validar_rangos_fechas(self) -> bool:
        """Valida que las fechas estén en rangos esperados"""
        print("\n[7] Validando rangos de fechas...")
        
        try:
            with self.conectar() as conn:
                query = f"""
                SELECT 
                    MIN(fecha_ingreso) as min_ingreso,
                    MAX(fecha_ingreso) as max_ingreso,
                    MIN(fecha_actualizacion) as min_actualizacion,
                    MAX(fecha_actualizacion) as max_actualizacion
                FROM {self.tabla}
                """
                rangos = pd.read_sql(query, conn)
                
                print(f"  Rango fecha_ingreso:")
                print(f"    Mínima: {rangos['min_ingreso'].values[0]}")
                print(f"    Máxima: {rangos['max_ingreso'].values[0]}")
                
                print(f"\n  Rango fecha_actualizacion:")
                print(f"    Mínima: {rangos['min_actualizacion'].values[0]}")
                print(f"    Máxima: {rangos['max_actualizacion'].values[0]}")
                
                # Validar que las fechas estén dentro del rango esperado
                min_ingreso = pd.to_datetime(rangos['min_ingreso'].values[0])
                max_ingreso = pd.to_datetime(rangos['max_ingreso'].values[0])
                
                fecha_min_esperada = pd.to_datetime(METRICAS_ESPERADAS['fecha_min'])
                fecha_max_esperada = pd.to_datetime(METRICAS_ESPERADAS['fecha_max'])
                
                if min_ingreso >= fecha_min_esperada and max_ingreso <= fecha_max_esperada:
                    self.agregar_resultado(
                        "Rangos de fechas", 
                        "[OK] PASS", 
                        f"Fechas dentro del rango esperado"
                    )
                    print(f"\n  [OK] Fechas dentro del rango esperado")
                    return True
                else:
                    self.agregar_resultado(
                        "Rangos de fechas", 
                        "[!] WARNING", 
                        f"Fechas fuera del rango esperado ({METRICAS_ESPERADAS['fecha_min']} - {METRICAS_ESPERADAS['fecha_max']})"
                    )
                    print(f"\n  [!] Algunas fechas fuera del rango esperado")
                    return False
                    
        except Exception as e:
            self.agregar_resultado("Rangos de fechas", "[ERROR] ERROR", str(e))
            print(f"  [ERROR] ERROR: {e}")
            return False
    
    # =========================================================================
    # VALIDACIONES DE CALIDAD
    # =========================================================================
    
    def validar_consistencia_datos(self) -> Dict:
        """Valida consistencia de datos numéricos"""
        print("\n[8] Validando consistencia de datos numéricos...")
        
        issues = []
        
        try:
            with self.conectar() as conn:
                # 1. Cantidad vs Cantidad Solicitada
                query = f"""
                SELECT COUNT(*) as registros
                FROM {self.tabla}
                WHERE cantidad > cantidad_solicitada
                """
                cant_mayor = pd.read_sql(query, conn)['registros'].values[0]
                
                if cant_mayor > 0:
                    issues.append(f"{cant_mayor:,} registros con cantidad > cantidad_solicitada")
                    print(f"  [!] {cant_mayor:,} registros con cantidad > cantidad_solicitada")
                else:
                    print(f"  [OK] Cantidades consistentes")
                
                # 2. Valores negativos
                query = f"""
                SELECT COUNT(*) as registros
                FROM {self.tabla}
                WHERE cantidad < 0 OR cantidad_solicitada < 0 OR total < 0
                """
                negativos = pd.read_sql(query, conn)['registros'].values[0]
                
                if negativos > 0:
                    issues.append(f"{negativos:,} registros con valores negativos")
                    print(f"  [FAIL] {negativos:,} registros con valores negativos")
                else:
                    print(f"  [OK] Sin valores negativos")
                
                # 3. Totales en 0 con cantidades
                query = f"""
                SELECT COUNT(*) as registros
                FROM {self.tabla}
                WHERE total = 0 AND cantidad > 0
                """
                total_cero = pd.read_sql(query, conn)['registros'].values[0]
                
                if total_cero > 0:
                    print(f"  [ℹ] {total_cero:,} registros con total=0 pero cantidad>0 (puede ser normal)")
                
                if len(issues) == 0:
                    self.agregar_resultado(
                        "Consistencia numérica", 
                        "[OK] PASS", 
                        "Datos numéricos consistentes"
                    )
                else:
                    self.agregar_resultado(
                        "Consistencia numérica", 
                        "[!] WARNING", 
                        "; ".join(issues)
                    )
                
                return {
                    'cantidad_mayor': cant_mayor,
                    'negativos': negativos,
                    'total_cero': total_cero
                }
                
        except Exception as e:
            self.agregar_resultado("Consistencia numérica", "[ERROR] ERROR", str(e))
            print(f"  [ERROR] ERROR: {e}")
            return {}
    
    # =========================================================================
    # REPORTE FINAL
    # =========================================================================
    
    def generar_reporte(self) -> str:
        """Genera reporte final de validación"""
        
        total_validaciones = len(self.resultados)
        passed = sum(1 for r in self.resultados if r['resultado'] == '[OK] PASS')
        failed = sum(1 for r in self.resultados if r['resultado'] == '[FAIL] FAIL')
        warnings = sum(1 for r in self.resultados if r['resultado'] == '[!] WARNING')
        errors = sum(1 for r in self.resultados if r['resultado'] == '[ERROR] ERROR')
        
        reporte = f"""
            {'='*70}
            REPORTE DE VALIDACIÓN - ETL ÓRDENES DE COMPRA
            {'='*70}
            Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            Base de datos: {self.db_path}
            Tabla: {self.tabla}

            RESUMEN:
            Total validaciones: {total_validaciones}
            [OK] Passed:   {passed}
            [FAIL] Failed:   {failed}
            [!] Warnings: {warnings}
            [ERROR] Errors:   {errors}

            DETALLE DE VALIDACIONES:
        """
        
        for idx, resultado in enumerate(self.resultados, 1):
            reporte += f"\n{idx}. {resultado['validacion']}: {resultado['resultado']}"
            if resultado['detalle']:
                reporte += f"\n   {resultado['detalle']}"
        
        if self.errores:
            reporte += f"\n\n{'='*70}\n"
            reporte += "ERRORES CRÍTICOS:\n"
            for idx, error in enumerate(self.errores, 1):
                reporte += f"{idx}. {error}\n"
        
        reporte += f"\n{'='*70}\n"
        
        if failed == 0 and errors == 0:
            reporte += "[OK] VALIDACIÓN EXITOSA - Todos los controles pasaron\n"
        elif failed > 0 or errors > 0:
            reporte += "[FAIL] VALIDACIÓN FALLIDA - Revisar errores críticos\n"
        else:
            reporte += "[!] VALIDACIÓN CON ADVERTENCIAS - Revisar warnings\n"
        
        reporte += f"{'='*70}\n"
        
        return reporte
    
    def ejecutar_todas(self) -> bool:
        """Ejecuta todas las validaciones"""
        print("="*70)
        print("EJECUTANDO VALIDACIONES".center(70))
        print("="*70)
        
        # Validaciones en orden
        if not self.validar_tabla_existe():
            return False
        
        self.validar_conteo_registros()
        self.validar_duplicados()
        self.validar_valores_nulos()
        self.validar_centros_distribucion()
        self.validar_estados()
        self.validar_rangos_fechas()
        self.validar_consistencia_datos()
        
        # Generar reporte
        print("\n" + "="*70)
        reporte = self.generar_reporte()
        print(reporte)
        
        # Guardar reporte
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join("reportes", f"reporte_validacion_{timestamp}.txt")
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(reporte)
        
        print(f"Reporte guardado en: {filename}")
        
        # Retornar True si no hay errores críticos
        return len(self.errores) == 0


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Función principal"""
    
    print("\n" + "="*70)
    print("VALIDACIÓN DE DATOS - ETL ÓRDENES DE COMPRA".center(70))
    print("="*70)
    print(f"Base de datos: {SQLITE_DB}")
    print(f"Tabla: {TABLA}")
    
    # Crear validador
    validador = DataValidator(SQLITE_DB, TABLA)
    
    # Ejecutar validaciones
    exito = validador.ejecutar_todas()
    
    # Exit code
    if exito:
        print("\n[OK] Todas las validaciones pasaron exitosamente")
        sys.exit(0)
    else:
        print("\n[FAIL] Algunas validaciones fallaron - Revisar reporte")
        sys.exit(1)


if __name__ == "__main__":
    main()
