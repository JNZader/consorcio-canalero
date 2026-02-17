"""
Test de conexion a Google Earth Engine con Service Account.

Ejecutar desde la raiz del proyecto:
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
from pathlib import Path

import pytest


@pytest.mark.skip(
    reason="Requires real GEE credentials and project; not suitable for automated test runs"
)
def test_connection():
    print("=" * 50)
    print("Test de conexion a Google Earth Engine")
    print("=" * 50)

    # 1. Cargar credenciales desde env o default
    key_path = os.getenv(
        "GEE_SERVICE_ACCOUNT_KEY", "./credentials/gee-service-account.json"
    )
    project_id = os.getenv("GEE_PROJECT_ID", "cc10demayo")

    # Si el path es relativo, buscar desde la raiz del proyecto
    if not os.path.isabs(key_path):
        root_dir = Path(__file__).parent.parent
        key_path = str(root_dir / key_path)

    if not os.path.exists(key_path):
        pytest.skip("GEE credentials file not found")

    print(f"\n[1] Cargando credenciales desde: {key_path}")
    try:
        with open(key_path) as f:
            key_data = json.load(f)
        print(f"    OK Email: {key_data['client_email']}")
    except FileNotFoundError:
        pytest.skip("GEE credentials file not found")
    except json.JSONDecodeError:
        pytest.fail("GEE credentials file is not valid JSON")

    # 2. Inicializar Earth Engine
    print(f"\n[2] Inicializando Earth Engine (proyecto: {project_id})")
    try:
        credentials = ee.ServiceAccountCredentials(key_data["client_email"], key_path)
        ee.Initialize(credentials, project=project_id)
        print("    OK Conexion exitosa!")
    except Exception as e:
        pytest.fail(f"Failed to initialize Earth Engine: {e}")

    # 3. Test basico - obtener info de una imagen
    print("\n[3] Probando acceso a datos (imagen Sentinel-2)")
    try:
        image = ee.Image(
            "COPERNICUS/S2_SR_HARMONIZED/20231001T140051_20231001T140051_T20JLL"
        )
        info = image.getInfo()
        print(f"    OK Imagen accesible: {info['id']}")
        print(f"    OK Bandas: {len(info['bands'])}")
    except Exception as e:
        pytest.fail(f"Failed to access Sentinel-2 image: {e}")

    # 4. Test de assets del proyecto (opcional)
    print("\n[4] Verificando assets del proyecto")
    try:
        assets = ee.data.listAssets({"parent": f"projects/{project_id}/assets"})
        asset_list = assets.get("assets", [])
        if asset_list:
            print(f"    OK Assets encontrados: {len(asset_list)}")
            for asset in asset_list[:5]:
                print(f"      - {asset['name']}")
            if len(asset_list) > 5:
                print(f"      ... y {len(asset_list) - 5} mas")
        else:
            print(f"    INFO No hay assets en projects/{project_id}/assets")
            print("    -> Esto es normal si aun no has subido geometrias")
    except Exception as e:
        print(f"    INFO No se pudo listar assets: {e}")
        print("    -> Puede que no tengas assets aun (es normal)")

    # Resultado final
    print("\n" + "=" * 50)
    print("OK CONEXION EXITOSA - Earth Engine funciona!")
    print("=" * 50)
    print("\nProximos pasos:")
    print("1. Configura tu .env con las variables de Supabase")
    print("2. Levanta el backend: docker-compose up")
    print("3. Prueba el endpoint: GET /api/v1/health")


if __name__ == "__main__":
    test_connection()
