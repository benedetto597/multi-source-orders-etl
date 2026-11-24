
**Autor**: Edgar Benedetto  
**Fecha**: 2026-02-05  
**Fase**: 1 - Exploración  

---
# Fase 1 Exploración

## 📋 Descripción

Script de exploración que analiza las tablas del SQL Server origen para entender la estructura, calidad y características de los datos antes de diseñar el ETL.

---

## 🎯 Objetivos

- **Descubrir** la estructura de tablas y esquemas
- **Analizar** tipos de datos y rangos
- **Detectar** duplicados y problemas de calidad
- **Documentar** hallazgos detallados

---


## 📁 Archivos

```
1_Exploracion/
├── logs/
│    └── exploracion_sql_server.log                  # Log de exploracion (generado)
├── reportes/
│    ├── reporte_exploracion_20260207_114143.txt     # Reporte del resultado de la exploración (generado)
│    ├── reporte_exploracion_20260207_114212.txt     
│    ├── reporte_exploracion_20260207_114233.txt     
│    └── ...
├── 01_exploracion.py                                # Script principal de exploración de datos
└── README.md                  
```

---

## 🐛 Troubleshooting

### Warning: "pandas only supports SQLAlchemy..."

**Causa**: pandas prefiere SQLAlchemy sobre pyodbc directo

**Solución**:
```py
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}")
```

Crea un objeto de conexión SQLAlchemy hacia SQL Server usando el driver pyodbc.
1. ***create_engine***: es la función de SQLAlchemy que construye un "motor" de base de datos. Este motor no abre la conexión inmediatamente, sino que define cómo conectarse y gestiona un pool de conexiones cuando lo usas.

2. ***mssql+pyodbc://***: indica el dialecto (mssql) y el controlador (pyodbc) que se usarán para hablar con SQL Server.

3. ***?odbc_connect={conn_str}***: en lugar de escribir toda la cadena de conexión en formato URL, se pasa el string ODBC completo (conn_str) como parámetro. Esto es útil porque las cadenas ODBC pueden ser largas y contener opciones como autenticación, cifrado, etc.
---

### Error: "ODBC Driver 18 not found"

**Causa**: ODBC Driver 18 for SQL Server no instalado

**Solución**:
- **Windows**: Descargar de [Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- **Linux**: 
  ```bash
  sudo apt-get install unixodbc-dev
  ```
- **Mac**: 
  ```bash
  brew install unixodbc
  ```

---

### Error: "Login failed for user"

**Causa**: Credenciales incorrectas o permisos insuficientes

**Solución**:
1. Verificar credenciales en `SQL_SERVER_CONFIG`
2. Confirmar que el Service Principal tiene permisos de lectura
3. Verificar conectividad de red al servidor

---

### Error: "No module named 'pyodbc'"

**Solución**:
```bash
pip install pyodbc | py -m pip install pyodbc
```

---

### Error: "No module named 'pandas'"

**Solución**:
```bash
pip install pandas | py -m pip install pandas
```

---

## 🎯 Hallazgos Clave

Basado en la exploración, se identificó:

### Inconsistencias de Esquema

| Campo | Ubicación 1 | Ubicación 2 |
|-------|-------------|-------------|
| `id` | bigint | varchar(24) |
| `codigo_orden` | varchar(64) | int |
| `cantidad_solicitada` | varchar(32) | bigint |
| `fecha_ingreso` | varchar(64) | datetime2 |

**Impacto en ETL**: Será necesario normalizar tipos de datos

### Estadísticas

- **Ubicación 1**: 31,116 registros (2023-01-05 a 2025-03-07)
- **Ubicación 2**: 31,124 registros (2023-01-02 a 2024-02-29)
- **Duplicados**: 0 en ambas tablas (por ID)

