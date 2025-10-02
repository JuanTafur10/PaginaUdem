#!/usr/bin/env python3

import requests
import json

def test_profesor_login():
    """Probar el login del usuario profesor"""
    
    # URL base de la API
    base_url = "http://localhost:5000/api"
    
    # Datos de login del profesor
    login_data = {
        "correo": "profesor@udem.edu.co",
        "password": "123456"
    }
    
    try:
        print("🔍 Probando endpoint de test...")
        test_response = requests.get(f"{base_url}/test")
        print(f"✅ Test response: {test_response.json()}")
        
        print("\n🔐 Probando login del profesor...")
        login_response = requests.post(
            f"{base_url}/auth/login",
            json=login_data,
            headers={"Content-Type": "application/json"}
        )
        
        if login_response.status_code == 200:
            login_result = login_response.json()
            print(f"✅ Login exitoso!")
            print(f"   - Token: {login_result.get('access_token', 'No token')[:50]}...")
            print(f"   - Rol: {login_result.get('rol', 'No rol')}")
            print(f"   - Usuario: {login_result.get('user', {}).get('nombre', 'No nombre')}")
            return login_result
        else:
            print(f"❌ Error en login: {login_response.status_code}")
            print(f"   Respuesta: {login_response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Error: No se puede conectar con el servidor")
        print("   Asegúrate de que el servidor Flask esté funcionando en localhost:5000")
        return None
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return None

def test_create_convocatoria(token):
    """Probar la creación de una convocatoria con el token del profesor"""
    
    if not token:
        print("❌ No hay token disponible para probar")
        return
    
    base_url = "http://localhost:5000/api"
    
    # Datos de la convocatoria de prueba
    convocatoria_data = {
        "curso": "Programación Avanzada",
        "semestre": "5",
        "requisitos": "Promedio mínimo 4.0, conocimientos en Python"
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        print("\n📝 Probando creación de convocatoria...")
        response = requests.post(
            f"{base_url}/convocatorias",
            json=convocatoria_data,
            headers=headers
        )
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ Convocatoria creada exitosamente!")
            print(f"   - ID: {result.get('id', 'No ID')}")
            print(f"   - Curso: {result.get('curso', 'No curso')}")
            print(f"   - Estado: {result.get('estado', 'No estado')}")
            return result
        else:
            print(f"❌ Error creando convocatoria: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Iniciando pruebas del usuario profesor...")
    print("=" * 50)
    
    # Probar login
    login_result = test_profesor_login()
    
    if login_result:
        token = login_result.get('access_token')
        # Probar creación de convocatoria
        test_create_convocatoria(token)
    
    print("\n" + "=" * 50)
    print("🏁 Pruebas completadas")