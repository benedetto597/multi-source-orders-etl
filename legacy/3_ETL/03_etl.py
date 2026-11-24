"""
Fase 3 - ETL (Extract, Transform, Load)
==================================================
Extrae datos de SQL Server (históricos) y CSVs (incrementales),
transforma y consolida en SQLite. 
Con soporte para cargas incrementales

Autor: Edgar Benedetto
Fecha: 2026-02-07
Versión: 2.0
"""

import pandas as pd
import sqlite3
import glob
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from sqlalchemy import create_engine, text
import urllib.parse

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Configuración de modo incremental
INCREMENTAL_CONFIG = {
    'enabled': False,  # False para full refresh y True para incremental
    'lookback_months': 18,  # Ventana de meses a procesar
    'date_column': 'fecha_actualizacion',
    'fallback_column': 'fecha_ingreso',
    'use_upsert': True  # True = UPSERT, False = TRUNCATE+INSERT
}

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join("logs", "etl_ordenes_compra.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# SQL Server Configuration
SQL_SERVER_CONFIG = {
    'driver': 'ODBC Driver 18 for SQL Server',
    # Credenciales leídas de variables de entorno (nunca en el código)
    'server': os.environ.get('SQL_SERVER', ''),
    'database': os.environ.get('SQL_DATABASE', ''),
    'uid': os.environ.get('SQL_CLIENT_ID', ''),
    'pwd': os.environ.get('SQL_CLIENT_SECRET', ''),
    'authentication': 'ActiveDirectoryServicePrincipal',
    'encrypt': 'yes'
}

# Paths
CSV_DIRECTORIES = [
    './csvs/ubicacion_1',  # CSVs de ubicación 1
    './csvs/ubicacion_2'   # CSVs de ubicación 2
]

# Carpeta base donde está el ETL 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB = os.path.join(BASE_DIR, "..", "5_DestinoBD", "destino.db")
METADATA_FILE = os.path.join(BASE_DIR, "etl_metadata.json")

# Esquema destino
TABLA_DESTINO = 'ordenes_compra_consolidadas'

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS ordenes_compra_consolidadas (
    id TEXT NOT NULL,
    centro_distribucion TEXT NOT NULL,
    codigo_orden TEXT,
    codigo_producto INTEGER,
    estado TEXT,
    cantidad INTEGER,
    cantidad_solicitada INTEGER,
    total REAL,
    fecha_ingreso TIMESTAMP,
    fecha_actualizacion TIMESTAMP,
    codigo_proveedor TEXT,
    mes_act TEXT,
    fuente TEXT,
    fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, centro_distribucion)
);
"""

# Índices para optimización
INDICES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_centro ON ordenes_compra_consolidadas(centro_distribucion);",
    "CREATE INDEX IF NOT EXISTS idx_fecha_ingreso ON ordenes_compra_consolidadas(fecha_ingreso);",
    "CREATE INDEX IF NOT EXISTS idx_fecha_act ON ordenes_compra_consolidadas(fecha_actualizacion);",
    "CREATE INDEX IF NOT EXISTS idx_estado ON ordenes_compra_consolidadas(estado);"
]


# =============================================================================
# METADATA MANAGER
# =============================================================================

class MetadataManager:
    """Gestiona metadata para cargas incrementales"""
    
    def __init__(self, metadata_file: str):
        self.metadata_file = metadata_file
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Carga metadata del archivo JSON"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_metadata(self):
        """Guarda metadata al archivo JSON"""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2, default=str)
    
    def get_incremental_window(self) -> Tuple[datetime, datetime]:
        """Calcula ventana de fechas para carga incremental"""
        fecha_fin = datetime.now()
        meses = INCREMENTAL_CONFIG['lookback_months']
        fecha_inicio = fecha_fin - timedelta(days=30 * meses)
        return fecha_inicio, fecha_fin
    
    def update_watermark(self, source: str, watermark: datetime, records: int):
        """Actualiza watermark después de procesamiento"""
        if source not in self.metadata:
            self.metadata[source] = {}
        
        self.metadata[source].update({
            'last_watermark': watermark.isoformat(),
            'last_run': datetime.now().isoformat(),
            'records_processed': records,
            'status': 'success'
        })
        self._save_metadata()

# =============================================================================
# CLASE: SQL SERVER EXTRACTOR
# =============================================================================

class SQLServerExtractor:
    """Extrae datos desde SQL Server con soporte incremental"""
    
    def __init__(self, config: Dict, metadata_manager: Optional[MetadataManager] = None):
        self.config = config
        self.metadata_manager = metadata_manager
        self.conn_str = self._build_connection_string()
        self.engine = self._create_engine()
    
    def _build_connection_string(self) -> str:
        """Construye connection string para SQLAlchemy"""
        return (
            f"mssql+pyodbc://{self.config['uid']}:{urllib.parse.quote_plus(self.config['pwd'])}"
            f"@{self.config['server']}/{self.config['database']}"
            f"?driver={urllib.parse.quote_plus(self.config['driver'])}"
            f"&Authentication={self.config['authentication']}"
            f"&Encrypt={self.config['encrypt']}"
        )
    
    def _create_engine(self):
        """Crea SQLAlchemy engine"""
        return create_engine(self.conn_str)
    
    def extract_table(self, table_name: str, ubicacion: str) -> pd.DataFrame:
        """
        Extrae datos de una tabla con soporte incremental
        
        Args:
            table_name: Nombre de la tabla
            ubicacion: Identificador de centro
        
        Returns:
            DataFrame con datos extraídos
        """
        mode = "INCREMENTAL" if INCREMENTAL_CONFIG['enabled'] else "FULL"
        logger.info(f"Extrayendo datos de {table_name} (modo {mode})...")
        
        try:
            with self.engine.connect() as conn:
                # Aplicar filtro incremental si está habilitado
                if INCREMENTAL_CONFIG['enabled'] and self.metadata_manager:
                    fecha_inicio, fecha_fin = self.metadata_manager.get_incremental_window()
                    
                    query = text(f"""
                        SELECT * FROM {table_name}
                        WHERE (
                            {INCREMENTAL_CONFIG['date_column']} >= :fecha_inicio
                            OR (
                                {INCREMENTAL_CONFIG['date_column']} IS NULL 
                                AND {INCREMENTAL_CONFIG['fallback_column']} >= :fecha_inicio
                            )
                        )
                    """)
                    
                    df = pd.read_sql(query, conn, params={'fecha_inicio': fecha_inicio})
                    logger.info(f"  Filtro incremental: >= {fecha_inicio.date()}")
                else:
                    # Modo original: extraer todo
                    query = text(f"SELECT * FROM {table_name}")
                    df = pd.read_sql(query, conn)
                
                # Agregar metadata
                df['centro_distribucion'] = ubicacion
                df['fuente'] = f'sql_{ubicacion}'
                
                logger.info(f"[OK] Extraídos {len(df):,} registros de {table_name}")
                
                # Actualizar watermark si es incremental
                if INCREMENTAL_CONFIG['enabled'] and self.metadata_manager and len(df) > 0:
                    max_date = pd.to_datetime(df[INCREMENTAL_CONFIG['date_column']]).max()
                    if pd.notna(max_date):
                        self.metadata_manager.update_watermark(f'sql_{ubicacion}', max_date, len(df))
                
                return df
                
        except Exception as e:
            logger.error(f"Error extrayendo {table_name}: {e}")
            raise
    
    def extract_all_tables(self) -> pd.DataFrame:
        """Extrae todas las tablas de órdenes de compra"""
        
        tablas = [
            ('ordenes_compra_ubicacion_1', 'ubicacion_1'),
            ('ordenes_compra_ubicacion_2', 'ubicacion_2')
        ]
        
        dataframes = []
        for table_name, ubicacion in tablas:
            df = self.extract_table(table_name, ubicacion)
            dataframes.append(df)
        
        df_consolidado = pd.concat(dataframes, ignore_index=True)
        
        mode = "incremental" if INCREMENTAL_CONFIG['enabled'] else "completo"
        logger.info(f"Total datos SQL Server ({mode}): {len(df_consolidado):,} registros")
        
        return df_consolidado


# =============================================================================
# CLASE: CSV EXTRACTOR
# =============================================================================

class CSVExtractor:
    """Extrae y consolida datos de archivos CSV con soporte incremental"""
    
    def __init__(self, csv_directories: List[str], metadata_manager: Optional[MetadataManager] = None):
        self.csv_directories = csv_directories
        self.metadata_manager = metadata_manager
    
    def _get_required_months(self) -> Optional[set]:
        """Calcula qué meses necesitan procesarse en modo incremental"""
        if not INCREMENTAL_CONFIG['enabled'] or not self.metadata_manager:
            return None  # Procesar todos
        
        fecha_inicio, fecha_fin = self.metadata_manager.get_incremental_window()
        
        meses_necesarios = set()
        current = fecha_inicio
        while current <= fecha_fin:
            mes_str = current.strftime('%Y%m')
            meses_necesarios.add(mes_str)
            # Avanzar al siguiente mes
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        return meses_necesarios
    
    def extract_csvs(self) -> pd.DataFrame:
        """Extrae todos los CSVs con soporte incremental"""
        
        # Obtener meses requeridos si es incremental
        meses_necesarios = self._get_required_months()
        
        if meses_necesarios:
            logger.info(f"Modo incremental: procesando {len(meses_necesarios)} meses")
        
        all_csv_files = []
        
        for csv_dir in self.csv_directories:
            csv_pattern = os.path.join(csv_dir, 'ordenes_*.csv')
            csv_files = sorted(glob.glob(csv_pattern))
            
            # Filtrar CSVs si es incremental
            if meses_necesarios:
                csv_files_filtered = []
                for csv_file in csv_files:
                    filename = os.path.basename(csv_file)
                    try:
                        mes_archivo = filename.replace('ordenes_', '').replace('.csv', '')[:6]
                        if mes_archivo in meses_necesarios:
                            csv_files_filtered.append(csv_file)
                    except:
                        logger.warning(f"No se pudo parsear fecha del archivo: {filename}")
                csv_files = csv_files_filtered
            
            if csv_files:
                logger.info(f"Archivos a procesar en {os.path.basename(csv_dir)}: {len(csv_files)}")
                all_csv_files.extend(csv_files)
            else:
                logger.warning(f"No se encontraron CSVs en {csv_dir}")
        
        if not all_csv_files:
            logger.error("No se encontraron archivos CSV")
            return pd.DataFrame()
        
        mode = "incremental" if meses_necesarios else "completo"
        logger.info(f"Total archivos CSV a procesar ({mode}): {len(all_csv_files)}")
        
        dataframes = []
        for csv_file in all_csv_files:
            filename = os.path.basename(csv_file)
            carpeta = os.path.basename(os.path.dirname(csv_file))
            logger.info(f"Procesando {carpeta}/{filename}...")
            
            df = pd.read_csv(csv_file)
            
            # Identificar centro por carpeta
            if 'ubicacion_1' in csv_file:
                df['centro_distribucion'] = 'ubicacion_1'
            elif 'ubicacion_2' in csv_file:
                df['centro_distribucion'] = 'ubicacion_2'
            else:
                df['centro_distribucion'] = df['codigo_orden'].apply(
                    lambda x: 'ubicacion_1' if pd.notna(x) and str(int(x))[0] == '1' 
                    else 'ubicacion_2' if pd.notna(x) and str(int(x))[0] == '2'
                    else 'desconocido'
                )
            
            df['fuente'] = 'csv'
            dataframes.append(df)
            logger.info(f"  [OK] {len(df):,} registros - {df['centro_distribucion'].unique()[0]}")
        
        df_consolidado = pd.concat(dataframes, ignore_index=True)
        logger.info(f"Total datos CSVs ({mode}): {len(df_consolidado):,} registros")
        
        return df_consolidado


# =============================================================================
# CLASE: DATA TRANSFORMER
# =============================================================================

class DataTransformer:
    """Transforma y normaliza datos"""
    
    @staticmethod
    def normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza tipos de datos al esquema destino
        
        Args:
            df: DataFrame a normalizar
        
        Returns:
            DataFrame con esquema normalizado
        """
        logger.info("Normalizando esquema...")
        
        df_norm = df.copy()
        
        # Convertir ID a string (maneja tanto int como varchar)
        df_norm['id'] = df_norm['id'].astype(str)
        
        # Convertir codigo_orden a string (maneja floats en formato string)
        df_norm['codigo_orden'] = df_norm['codigo_orden'].apply(
            lambda x: str(int(float(x))) if pd.notna(x) else None
        )
        
        # Convertir codigo_producto a int
        df_norm['codigo_producto'] = df_norm['codigo_producto'].fillna(0).astype(int)
        
        # Convertir cantidad_solicitada (puede venir como varchar)
        if df_norm['cantidad_solicitada'].dtype == 'object':
            df_norm['cantidad_solicitada'] = pd.to_numeric(
                df_norm['cantidad_solicitada'], 
                errors='coerce'
            ).fillna(0).astype(int)
        
        # Parsear fechas
        df_norm['fecha_ingreso'] = pd.to_datetime(
            df_norm['fecha_ingreso'], 
            errors='coerce'
        )
        
        df_norm['fecha_actualizacion'] = pd.to_datetime(
            df_norm['fecha_actualizacion'], 
            errors='coerce'
        )
        
        # Convertir mes_act a string si existe
        if 'mes_act' in df_norm.columns:
            df_norm['mes_act'] = df_norm['mes_act'].apply(
                lambda x: str(int(float(x))) if pd.notna(x) else None
            )
        else:
            df_norm['mes_act'] = None
        
        logger.info("[OK] Esquema normalizado")
        return df_norm
    
    @staticmethod
    def add_metadata(df: pd.DataFrame) -> pd.DataFrame:
        """Agrega columnas de metadata"""
        df['fecha_carga'] = datetime.now()
        return df


# =============================================================================
# CLASE: DEDUPLICATOR
# =============================================================================

class Deduplicator:
    """Maneja la lógica de deduplicación"""
    
    @staticmethod
    def remove_duplicates(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        Elimina duplicados manteniendo el registro más reciente
        
        Strategy:
        1. Duplicados = mismo ID + mismo centro_distribucion
        2. Mantener registro con fecha_actualizacion más reciente
        3. Si fecha_actualizacion es NULL, usar fecha_ingreso
        
        Args:
            df: DataFrame con posibles duplicados
        
        Returns:
            (DataFrame sin duplicados, Diccionario con métricas)
        """
        logger.info("Iniciando deduplicación...")
        
        registros_iniciales = len(df)
        
        # Crear columna auxiliar para ordenar
        df['fecha_referencia'] = df['fecha_actualizacion'].fillna(df['fecha_ingreso'])
        
        # Identificar duplicados
        duplicados_mask = df.duplicated(
            subset=['id', 'centro_distribucion'], 
            keep=False
        )
        num_duplicados = duplicados_mask.sum()
        
        logger.info(f"Registros con duplicados detectados: {num_duplicados:,}")
        
        # Ordenar por fecha más reciente y mantener primero
        df_sorted = df.sort_values(
            by=['id', 'centro_distribucion', 'fecha_referencia'],
            ascending=[True, True, False]
        )
        
        # Eliminar duplicados manteniendo el primero (más reciente)
        df_dedup = df_sorted.drop_duplicates(
            subset=['id', 'centro_distribucion'],
            keep='first'
        )
        
        # Limpiar columna auxiliar
        df_dedup = df_dedup.drop(columns=['fecha_referencia'])
        
        registros_finales = len(df_dedup)
        registros_eliminados = registros_iniciales - registros_finales
        
        metricas = {
            'registros_iniciales': registros_iniciales,
            'registros_finales': registros_finales,
            'registros_eliminados': registros_eliminados,
            'grupos_duplicados': num_duplicados
        }
        
        logger.info(f"[OK] Deduplicación completada:")
        logger.info(f"  - Registros iniciales: {registros_iniciales:,}")
        logger.info(f"  - Registros eliminados: {registros_eliminados:,}")
        logger.info(f"  - Registros finales: {registros_finales:,}")
        
        return df_dedup, metricas


# =============================================================================
# CLASE: SQLITE LOADER
# =============================================================================

class SQLiteLoader:
    """Carga datos en SQLite con soporte UPSERT opcional"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def create_table(self):
        """Crea tabla destino con esquema definido"""
        logger.info(f"Creando tabla en {self.db_path}...")
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(ESQUEMA_SQL)
            
            for idx_sql in INDICES_SQL:
                conn.execute(idx_sql)
            
            conn.commit()
        
        logger.info("[OK] Tabla e índices creados")
    
    def truncate_table(self):
        """Limpia tabla destino (full refresh)"""
        logger.info("Limpiando tabla destino (TRUNCATE)...")
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM {TABLA_DESTINO}")
            conn.commit()
        
        logger.info("[OK] Tabla limpiada")
    
    def load_data(self, df: pd.DataFrame):
        """
        Carga datos con INSERT normal (modo full refresh)
        """
        logger.info(f"Cargando {len(df):,} registros a SQLite (INSERT)...")
        
        columnas = [
            'id', 'centro_distribucion', 'codigo_orden', 'codigo_producto',
            'estado', 'cantidad', 'cantidad_solicitada', 'total',
            'fecha_ingreso', 'fecha_actualizacion', 'codigo_proveedor',
            'mes_act', 'fuente', 'fecha_carga', 'fecha_modificacion'
        ]
        
        # Asegurar que todas las columnas existan
        for col in columnas:
            if col not in df.columns:
                df[col] = None if col not in ['fecha_carga', 'fecha_modificacion'] else datetime.now()
        
        df_load = df[columnas].copy()
        
        # Convertir Timestamps a strings para SQLite
        date_columns = ['fecha_ingreso', 'fecha_actualizacion', 'fecha_carga', 'fecha_modificacion']
        for col in date_columns:
            if col in df_load.columns:
                df_load[col] = df_load[col].apply(
                    lambda x: x.isoformat() if pd.notna(x) else None
                )
        
        with sqlite3.connect(self.db_path) as conn:
            df_load.to_sql(
                TABLA_DESTINO,
                conn,
                if_exists='append',
                index=False
            )
        
        logger.info("[OK] Datos cargados exitosamente")
    
    def upsert_data(self, df: pd.DataFrame):
        """
        Carga datos con UPSERT (modo incremental)
        UPDATE existentes + INSERT nuevos
        """
        logger.info(f"Iniciando UPSERT de {len(df):,} registros...")
        
        columnas = [
            'id', 'centro_distribucion', 'codigo_orden', 'codigo_producto',
            'estado', 'cantidad', 'cantidad_solicitada', 'total',
            'fecha_ingreso', 'fecha_actualizacion', 'codigo_proveedor',
            'mes_act', 'fuente', 'fecha_carga', 'fecha_modificacion'
        ]
        
        # Asegurar columnas
        for col in columnas:
            if col not in df.columns:
                df[col] = datetime.now() if col in ['fecha_carga', 'fecha_modificacion'] else None
        
        df_load = df[columnas].copy()
        
        # Convertir Timestamps a strings para SQLite
        date_columns = ['fecha_ingreso', 'fecha_actualizacion', 'fecha_carga', 'fecha_modificacion']
        for col in date_columns:
            if col in df_load.columns:
                df_load[col] = df_load[col].apply(
                    lambda x: x.isoformat() if pd.notna(x) else None
                )
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            updates = 0
            inserts = 0
            
            for idx, row in df_load.iterrows():
                # Verificar si existe
                cursor.execute(
                    f"SELECT COUNT(*) FROM {TABLA_DESTINO} WHERE id = ? AND centro_distribucion = ?",
                    (row['id'], row['centro_distribucion'])
                )
                exists = cursor.fetchone()[0] > 0
                
                if exists:
                    # UPDATE
                    update_sql = f"""
                    UPDATE {TABLA_DESTINO}
                    SET codigo_orden = ?, codigo_producto = ?, estado = ?,
                        cantidad = ?, cantidad_solicitada = ?, total = ?,
                        fecha_ingreso = ?, fecha_actualizacion = ?,
                        codigo_proveedor = ?, mes_act = ?, fuente = ?,
                        fecha_modificacion = ?
                    WHERE id = ? AND centro_distribucion = ?
                    """
                    cursor.execute(update_sql, (
                        row['codigo_orden'], row['codigo_producto'], row['estado'],
                        row['cantidad'], row['cantidad_solicitada'], row['total'],
                        row['fecha_ingreso'], row['fecha_actualizacion'],
                        row['codigo_proveedor'], row['mes_act'], row['fuente'],
                        row['fecha_modificacion'],
                        row['id'], row['centro_distribucion']
                    ))
                    updates += 1
                else:
                    # INSERT
                    insert_sql = f"""
                    INSERT INTO {TABLA_DESTINO} (
                        id, centro_distribucion, codigo_orden, codigo_producto,
                        estado, cantidad, cantidad_solicitada, total,
                        fecha_ingreso, fecha_actualizacion, codigo_proveedor,
                        mes_act, fuente, fecha_carga, fecha_modificacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    cursor.execute(insert_sql, tuple(row))
                    inserts += 1
                
                # Commit cada 1000 registros
                if (updates + inserts) % 1000 == 0:
                    conn.commit()
                    logger.info(f"  Progreso: {updates + inserts:,} / {len(df):,}")
            
            conn.commit()
        
        logger.info(f"[OK] UPSERT completado:")
        logger.info(f"  - Registros insertados: {inserts:,}")
        logger.info(f"  - Registros actualizados: {updates:,}")
    
    def validate_load(self) -> Dict:
        """Valida la carga de datos"""
        logger.info("Validando carga...")
        
        with sqlite3.connect(self.db_path) as conn:
            total = pd.read_sql(
                f"SELECT COUNT(*) as total FROM {TABLA_DESTINO}", 
                conn
            )['total'].values[0]
            
            por_centro = pd.read_sql(
                f"SELECT centro_distribucion, COUNT(*) as total FROM {TABLA_DESTINO} GROUP BY centro_distribucion",
                conn
            )
            
            por_fuente = pd.read_sql(
                f"SELECT fuente, COUNT(*) as total FROM {TABLA_DESTINO} GROUP BY fuente",
                conn
            )
            
            duplicados = pd.read_sql(
                f"""
                SELECT COUNT(*) as duplicados 
                FROM (
                    SELECT id, centro_distribucion, COUNT(*) as cnt
                    FROM {TABLA_DESTINO}
                    GROUP BY id, centro_distribucion
                    HAVING COUNT(*) > 1
                )
                """,
                conn
            )['duplicados'].values[0]
        
        metricas = {
            'total_registros': total,
            'por_centro': por_centro.to_dict('records'),
            'por_fuente': por_fuente.to_dict('records'),
            'duplicados': duplicados
        }
        
        logger.info(f"[OK] Validación completada:")
        logger.info(f"  - Total registros: {total:,}")
        logger.info(f"  - Duplicados: {duplicados}")
        
        return metricas


# =============================================================================
# ORQUESTADOR PRINCIPAL
# =============================================================================

def main():
    """Pipeline ETL principal con soporte incremental opcional"""
    
    logger.info("="*70)
    
    # Mostrar modo de operación
    if INCREMENTAL_CONFIG['enabled']:
        logger.info("INICIANDO ETL - MODO INCREMENTAL".center(70))
        logger.info(f"Ventana: últimos {INCREMENTAL_CONFIG['lookback_months']} meses")
    else:
        logger.info("INICIANDO ETL - MODO FULL REFRESH".center(70))
    
    logger.info("="*70)
    
    inicio = datetime.now()
    
    try:
        # Inicializar metadata manager si es incremental
        metadata_manager = None
        if INCREMENTAL_CONFIG['enabled']:
            metadata_manager = MetadataManager(METADATA_FILE)
            fecha_inicio, fecha_fin = metadata_manager.get_incremental_window()
            logger.info(f"Ventana incremental: {fecha_inicio.date()} a {fecha_fin.date()}")
        
        # =====================================================================
        # EXTRACT
        # =====================================================================
        logger.info("\n[FASE 1: EXTRACCIÓN]")
        
        # Extraer SQL Server (con metadata_manager si es incremental)
        sql_extractor = SQLServerExtractor(SQL_SERVER_CONFIG, metadata_manager)
        df_sql = sql_extractor.extract_all_tables()
        
        # Extraer CSVs (con metadata_manager si es incremental)
        csv_extractor = CSVExtractor(CSV_DIRECTORIES, metadata_manager)
        df_csv = csv_extractor.extract_csvs()
        
        # Consolidar fuentes
        df_raw = pd.concat([df_sql, df_csv], ignore_index=True)
        logger.info(f"\nTotal datos extraídos: {len(df_raw):,} registros")
        
        # =====================================================================
        # TRANSFORM
        # =====================================================================
        logger.info("\n[FASE 2: TRANSFORMACIÓN]")
        
        transformer = DataTransformer()
        df_transformed = transformer.normalize_schema(df_raw)
        df_transformed = transformer.add_metadata(df_transformed)
        
        # =====================================================================
        # DEDUPLICATE
        # =====================================================================
        logger.info("\n[FASE 3: DEDUPLICACIÓN]")
        
        deduplicator = Deduplicator()
        df_clean, metricas_dedup = deduplicator.remove_duplicates(df_transformed)
        
        # =====================================================================
        # LOAD
        # =====================================================================
        logger.info("\n[FASE 4: CARGA]")
        
        loader = SQLiteLoader(SQLITE_DB)
        loader.create_table()
        
        # Elegir estrategia según configuración
        if INCREMENTAL_CONFIG['enabled'] and INCREMENTAL_CONFIG['use_upsert']:
            logger.info("Estrategia: UPSERT (incremental)")
            loader.upsert_data(df_clean)
        else:
            logger.info("Estrategia: TRUNCATE + INSERT (full refresh)")
            loader.truncate_table()
            loader.load_data(df_clean)
        
        # =====================================================================
        # VALIDATE
        # =====================================================================
        logger.info("\n[FASE 5: VALIDACIÓN]")
        
        metricas_validacion = loader.validate_load()
        
        # =====================================================================
        # RESUMEN FINAL
        # =====================================================================
        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()
        
        logger.info("\n")
        logger.info("="*70)
        logger.info("ETL COMPLETADO EXITOSAMENTE".center(70))
        logger.info("="*70)
        logger.info(f"Modo: {'INCREMENTAL' if INCREMENTAL_CONFIG['enabled'] else 'FULL REFRESH'}")
        logger.info(f"Duración: {duracion:.2f} segundos")
        logger.info(f"\nRESUMEN:")
        logger.info(f"  - Registros extraídos: {len(df_raw):,}")
        logger.info(f"  - Registros duplicados eliminados: {metricas_dedup['registros_eliminados']:,}")
        logger.info(f"  - Registros totales cargados: {metricas_validacion['total_registros']:,}")
        logger.info(f"  - Duplicados en destino: {metricas_validacion['duplicados']}")
        logger.info(f"\nDISTRIBUCIÓN POR CENTRO:")
        for centro in metricas_validacion['por_centro']:
            logger.info(f"  - {centro['centro_distribucion']}: {centro['total']:,} registros")
        
        if metricas_validacion['duplicados'] > 0:
            logger.warning("[!] ATENCIÓN: Se encontraron duplicados en destino")
        else:
            logger.info("[OK] Integridad de datos verificada: 0 duplicados")
        
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] ERROR EN ETL: {e}")
        logger.exception("Detalles del error:")
        return False


if __name__ == "__main__":
    exito = main()
    exit(0 if exito else 1)