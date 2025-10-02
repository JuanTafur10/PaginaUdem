@echo off
echo ========================================
echo      INICIANDO PROYECTO UDEM
echo ========================================

echo.
echo 1. Iniciando la base de datos...
cd backend
python init_db.py

echo.
echo 2. Iniciando el servidor Flask...
echo El backend estará disponible en: http://localhost:5000
echo.
echo Para probar la API manualmente:
echo - Login: POST http://localhost:5000/api/auth/login
echo - Convocatorias activas: GET http://localhost:5000/api/convocatorias/activas
echo.
echo Presiona Ctrl+C para detener el servidor
echo.

python manage.py