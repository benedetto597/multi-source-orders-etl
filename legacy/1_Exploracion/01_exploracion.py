""" 
Fase 1 - Exploracion
========================================
Este script realiza una exploración de las tablas del SQL Server origen.

Autor: Edgar Benedetto
Fecha: 2026-02-05
Versión: 1.0
"""

import pandas as pd
import logging
import os
from datetime import datetime
from sqlalchemy import create_engine

# Crear carpetas para logs y reportes si no existen 
os.makedirs("logs", exist_ok=True) 
os.makedirs("reportes", exist_ok=True)

# Configuración de logging
logging.basicConfig(
    filename=os.path.join("logs", "exploracion_sql_server.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Archivo de salida para el reporte en texto
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTPUT_FILE = os.path.join("reportes", f"reporte_exploracion_{timestamp}.txt")

def print_and_save(text: str, file):
    """Imprime en consola y guarda en archivo .txt"""
    print(text)
    file.write(text + "\n")

def print_header(title: str, file, width: int = 80, char: str = "="):
    """Imprime un encabezado ASCII-safe en consola y archivo"""
    line = char * width
    print_and_save("\n" + line, file)
    print_and_save(title.center(width), file)
    print_and_save(line, file)

def explorar_sql_server():
    """Explora las tablas del SQL Server origen"""
    
    # Credenciales leídas de variables de entorno (nunca en el código)
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_CLIENT_ID']};"
        f"PWD={os.environ['SQL_CLIENT_SECRET']};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        "Encrypt=yes;"
    )
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        print_header(f"EXPLORACIÓN DE BASE DE DATOS - {datetime.now()}", f)
        logging.info("Inicio de exploración de base de datos")
        
        try:
            engine = create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}")
            with engine.connect() as conn:
                # 1. Listar tablas
                df_tables = pd.read_sql("SELECT name FROM sys.tables", conn)
                print_header(f"TABLAS ENCONTRADAS: {len(df_tables)}", f)
                print_and_save(df_tables.to_string(index=False), f)
                logging.info(f"Tablas encontradas: {len(df_tables)}")
                
                # 2. Para cada tabla, obtener info detallada
                for table_name in df_tables['name']:
                    print_header(f"TABLA: {table_name}", f)
                    logging.info(f"Explorando tabla: {table_name}")
                    
                    # 3. Esquema
                    schema_query = f"""
                    SELECT 
                        COLUMN_NAME, 
                        DATA_TYPE, 
                        IS_NULLABLE,
                        CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = '{table_name}'
                    ORDER BY ORDINAL_POSITION
                    """
                    df_schema = pd.read_sql(schema_query, conn)
                    print_and_save("\nESQUEMA:", f)
                    print_and_save(df_schema.to_string(index=False), f)
                    
                    # 4. Conteo
                    count_query = f"SELECT COUNT(*) as total FROM {table_name}"
                    total = pd.read_sql(count_query, conn)['total'].values[0]
                    print_and_save(f"\nTOTAL REGISTROS: {total:,}", f)
                    
                    # 5. Muestra
                    sample_query = f"SELECT TOP 5 * FROM {table_name}"
                    df_sample = pd.read_sql(sample_query, conn)
                    print_and_save("\nMUESTRA (5 registros):", f)
                    print_and_save(df_sample.to_string(index=False), f)
                    
                    # 6. Rango de fechas si existe columna de fecha
                    date_cols = df_schema[df_schema['DATA_TYPE'].str.contains('date', case=False, na=False)]['COLUMN_NAME'].tolist()
                    if date_cols:
                        date_col = date_cols[0]
                        range_query = f"SELECT MIN({date_col}) as min_fecha, MAX({date_col}) as max_fecha FROM {table_name}"
                        df_range = pd.read_sql(range_query, conn)
                        print_and_save(f"\nRANGO DE FECHAS ({date_col}):", f)
                        print_and_save(df_range.to_string(index=False), f)
                    
                    # 7. Verificar duplicados (si existe una columna ID)
                    id_cols = [col for col in df_schema['COLUMN_NAME'].tolist() if 'id' in col.lower()]
                    if id_cols:
                        id_col = id_cols[0]
                        dup_query = f"""
                        SELECT COUNT(*) as duplicados 
                        FROM (
                            SELECT {id_col}, COUNT(*) as cnt
                            FROM {table_name}
                            GROUP BY {id_col}
                            HAVING COUNT(*) > 1
                        ) t
                        """
                        duplicados = pd.read_sql(dup_query, conn)['duplicados'].values[0]
                        print_and_save(f"\nDUPLICADOS en '{id_col}': {duplicados}", f)
                    
                    print_and_save("\n", f)
                    
            print_header(f"FIN EXITOSO DE EXPLORACIÓN DE BASE DE DATOS - {datetime.now()}", f)
            logging.info("Reporte exportado a reporte_exploracion.txt")
        
        except Exception as e:
            print_header("ERROR", f)
            print_and_save(f"Mensaje: {e}", f)
            print_and_save(f"Tipo de error: {type(e).__name__}", f)
            logging.error(f"Error en exploración: {e} ({type(e).__name__})")

if __name__ == "__main__":
    explorar_sql_server()
