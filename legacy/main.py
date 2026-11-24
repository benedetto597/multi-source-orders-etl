"""
Orquestador maestro
========================================
Ejecuta en orden cada fase del proyecto:
- 1_Exploracion/01_exploracion.py
- 2_Arquitectura/02_esquema.py
- 3_ETL/03_etl.py
- 4_Validacion/04_validacion.py

Autor: Edgar Benedetto
Fecha: 2026-02-07
Versión: 1.0
"""

import subprocess
import os

# Carpeta base (donde está este main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Lista de scripts a ejecutar con sus carpetas
SCRIPTS = [
    ("1_Exploracion", "01_exploracion.py"),
    ("2_Arquitectura", "02_esquema.py"),
    ("3_ETL", "03_etl.py"),
    ("4_Validacion", "04_validacion.py"),
]

def run_script(folder, script):
    """Ejecuta un script en su carpeta correspondiente"""
    script_path = os.path.join(BASE_DIR, folder, script)
    cwd_path = os.path.join(BASE_DIR, folder)

    print("="*70)
    print(f"Ejecutando {script} en carpeta {folder}...".center(70))
    print("="*70)

    result = subprocess.run(
        ["python", script_path],
        cwd=cwd_path,   # mantiene el directorio de trabajo del hijo
        check=False     # no detiene main.py si hay error
    )

    print(f"Finalizado {script} con código {result.returncode}".center(70))
    print("="*70)

def main():
    for folder, script in SCRIPTS:
        run_script(folder, script)

if __name__ == "__main__":
    main()
