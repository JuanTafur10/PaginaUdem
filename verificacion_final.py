#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de verificación final - HU-01 y HU-02
"""
import requests
import json
import re
from datetime import datetime, timedelta

BASE_URL = "http://localhost:5000/api"

def verificar_clases():
    """Verificar que existen al menos 30 clases en models.py"""
    try:
        with open("backend/app/models.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Buscar definiciones de clases
        class_pattern = r'^class\s+(\w+)'
        matches = re.findall(class_pattern, content, re.MULTILINE)
        
        # Filtrar clases que no son de SQLAlchemy
        actual_classes = [cls for cls in matches if cls not in ['object', 'Base']]
        
        print(f"🔍 VERIFICACIÓN DE CLASES: {len(actual_classes)} encontradas")
        for i, cls in enumerate(actual_classes, 1):
            print(f"   {i:2d}. {cls}")
        
        if len(actual_classes) >= 30:
            print(f"✅ Se encontraron {len(actual_classes)} clases (≥30 requeridas)")
            return True
        else:
            print(f"❌ Solo se encontraron {len(actual_classes)} clases (<30 requeridas)")
            return False
            
    except Exception as e:
        print(f"❌ Error al verificar clases: {e}")
        return False

def main():
    print("=" * 70)
    print("🚀 VERIFICACIÓN FINAL DE LAS 30 CLASES Y HU-01/HU-02")
    print("=" * 70)
    
    # 0. Verificar las 30 clases primero
    if not verificar_clases():
        print("\n❌ FALLA EN VERIFICACIÓN DE CLASES - DETENIENDO")
        return
    
    # 1. Verificar que el servidor esté funcionando
    try:
        response = requests.get(f"{BASE_URL}/test", timeout=5)
        if response.status_code == 200:
            print("✅ Servidor funcionando correctamente")
        else:
            print("❌ Servidor no responde correctamente")
            return
    except:
        print("❌ No se puede conectar al servidor")
        return
    
    # 2. Login como coordinador
    try:
        login_data = {
            "correo": "coordinador@udem.edu.co",
            "password": "123456"
        }
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data, timeout=5)
        if response.status_code == 200:
            token = response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            print("✅ Login como coordinador exitoso")
        else:
            print("❌ Error en login")
            return
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return
    
    # 3. HU-01: Crear convocatoria
    print("\n📝 VERIFICANDO HU-01: CREAR CONVOCATORIA...")
    try:
        convocatoria_data = {
            "curso": "Algoritmos y Estructuras de Datos - Test",
            "semestre": "2024-2",
            "requisitos": "Promedio académico mínimo 4.0, haber cursado Programación I"
        }
        
        response = requests.post(f"{BASE_URL}/convocatorias", json=convocatoria_data, headers=headers, timeout=5)
        if response.status_code == 201:
            conv_data = response.json()
            conv_id = conv_data["id"]
            print("✅ HU-01: Convocatoria creada exitosamente")
            print(f"   📋 ID: {conv_id}")
            print(f"   📚 Curso: {conv_data['curso']}")
            print(f"   📅 Semestre: {conv_data['semestre']}")
            print(f"   ⚙️  Estado: {conv_data['estado']}")
        else:
            print(f"❌ HU-01: Error al crear convocatoria - Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return
            
    except Exception as e:
        print(f"❌ HU-01: Excepción: {e}")
        return
    
    # 4. Verificar listado público
    try:
        response = requests.get(f"{BASE_URL}/convocatorias", timeout=5)
        if response.status_code == 200:
            convocatorias = response.json()
            found = any(c["id"] == conv_id for c in convocatorias)
            if found:
                print("✅ HU-01: Convocatoria aparece en listado público")
            else:
                print("❌ HU-01: Convocatoria no aparece en listado")
        else:
            print(f"❌ HU-01: Error al obtener listado: {response.status_code}")
    except Exception as e:
        print(f"❌ HU-01: Error en listado: {e}")
    
    # 5. HU-02: Asignar fechas
    print("\n📅 VERIFICANDO HU-02: ASIGNAR FECHAS...")
    try:
        # Fechas válidas en el futuro
        fecha_apertura = (datetime.now() + timedelta(days=2)).isoformat()
        fecha_cierre = (datetime.now() + timedelta(days=30)).isoformat()
        
        fechas_data = {
            "fecha_apertura": fecha_apertura,
            "fecha_cierre": fecha_cierre
        }
        
        response = requests.patch(f"{BASE_URL}/convocatorias/{conv_id}/fechas", json=fechas_data, headers=headers, timeout=5)
        if response.status_code == 200:
            updated_conv = response.json()
            print("✅ HU-02: Fechas asignadas correctamente")
            print(f"   📅 Apertura: {updated_conv['fecha_apertura']}")
            print(f"   📅 Cierre: {updated_conv['fecha_cierre']}")
            print(f"   ⚙️  Estado: {updated_conv['estado']}")
        else:
            print(f"❌ HU-02: Error al asignar fechas - Status: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"❌ HU-02: Excepción: {e}")
    
    # 6. Test de validación: fecha en el pasado
    try:
        fechas_invalidas = {
            "fecha_cierre": (datetime.now() - timedelta(days=1)).isoformat()
        }
        
        response = requests.patch(f"{BASE_URL}/convocatorias/{conv_id}/fechas", json=fechas_invalidas, headers=headers, timeout=5)
        if response.status_code == 400:
            print("✅ HU-02: Sistema rechaza fechas en el pasado correctamente")
        else:
            print("❌ HU-02: Sistema no valida fechas correctamente")
            
    except Exception as e:
        print(f"❌ HU-02: Error en validación: {e}")
    
    print("\n" + "=" * 70)
    print("🎯 VERIFICACIÓN COMPLETADA")
    print("=" * 70)

if __name__ == "__main__":
    main()