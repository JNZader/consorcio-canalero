"""
Test de conexión a Google Earth Engine con Service Account.

Ejecutar desde la raíz del proyecto:
    python -m tests.test_gee_connection

O directamente:
    python tests/test_gee_connection.py

Requiere:
    - GEE_SERVICE_ACCOUNT_KEY: Path al archivo JSON de credenciales
    - GEE_PROJECT_ID: ID del proyecto en GCP (default: cc10demayo)
"""

import ee
import json
import os
import sys
from pathlib import Path


def test_connection():
    print("=" * 50)
    print("Test de conexión a Google Earth Engine")
    print("=" * 50)

    # 1. Cargar credenciales desde env o default
    key_path = os.getenv("GEE_SERVICE_ACCOUNT_KEY", "./credentials/gee-service-account.json")
    project_id = os.getenv("GEE_PROJECT_ID", "cc10demayo")

    # Si el path es relativo, buscar desde la raíz del proyecto
    if not os.path.isabs(key_path):
        root_dir = Path(__file__).parent.parent
        key_path = str(root_dir / key_path)

    print(f"\n[1] Cargando credenciales desde: {key_path}")
    try:
        with open(key_path) as f:
            key_data = json.load(f)
        print(f"    ✓ Email: {key_data['client_email']}")
    except FileNotFoundError:
        print(f"    ✗ ERROR: No se encontró el archivo {key_path}")
        print("    → Asegúrate de guardar el JSON de la service account ahí")
        print("    → O configura GEE_SERVICE_ACCOUNT_KEY en el entorno")
        sys.exit(1)
    except json.JSONDecodeError:
        print("    ✗ ERROR: El archivo no es un JSON válido")
        sys.exit(1)

    # 2. Inicializar Earth Engine
    print(f"\n[2] Inicializando Earth Engine (proyecto: {project_id})")
    try:
        credentials = ee.ServiceAccountCredentials(
            key_data["client_email"],
            key_path
        )
        ee.Initialize(credentials, project=project_id)
        print("    ✓ Conexión exitosa!")
    except Exception as e:
        print(f"    ✗ ERROR: {e}")
        sys.exit(1)

    # 3. Test básico - obtener info de una imagen
    print("\n[3] Probando acceso a datos (imagen Sentinel-2)")
    try:
        image = ee.Image("COPERNICUS/S2_SR_HARMONIZED/20231001T140051_20231001T140051_T20JLL")
        info = image.getInfo()
        print(f"    ✓ Imagen accesible: {info['id']}")
        print(f"    ✓ Bandas: {len(info['bands'])}")
    except Exception as e:
        print(f"    ✗ ERROR accediendo a imagen: {e}")
        sys.exit(1)

    # 4. Test de assets del proyecto (opcional)
    print("\n[4] Verificando assets del proyecto")
    try:
        assets = ee.data.listAssets({"parent": f"projects/{project_id}/assets"})
        asset_list = assets.get("assets", [])
        if asset_list:
            print(f"    ✓ Assets encontrados: {len(asset_list)}")
            for asset in asset_list[:5]:
                print(f"      - {asset['name']}")
            if len(asset_list) > 5:
                print(f"      ... y {len(asset_list) - 5} más")
        else:
            print(f"    ℹ No hay assets en projects/{project_id}/assets")
            print("    → Esto es normal si aún no has subido geometrías")
    except Exception as e:
        print(f"    ℹ No se pudo listar assets: {e}")
        print("    → Puede que no tengas assets aún (es normal)")

    # Resultado final
    print("\n" + "=" * 50)
    print("✓ CONEXIÓN EXITOSA - Earth Engine funciona!")
    print("=" * 50)
    print("\nPróximos pasos:")
    print("1. Configura tu .env con las variables de Supabase")
    print("2. Levanta el backend: docker-compose up")
    print("3. Prueba el endpoint: GET /api/v1/health")


if __name__ == "__main__":
    test_connection()
