@echo off
REM Bienestar Nexum - Escritorio (XML). Abre el programa.
setlocal
cd /d "%~dp0"

if not exist "entorno\Scripts\python.exe" (
    echo  Todavia no esta instalado. Corre primero Instalar.bat
    pause
    exit /b 1
)

REM Los XSD son los del repositorio, no una copia aparte.
set "CONTRATOS_XSD=%~dp0..\..\contratos\xml"

if "%AUTH_SERVICE_URL%"==""          set "AUTH_SERVICE_URL=http://127.0.0.1:8101"
if "%USERS_SERVICE_URL%"==""         set "USERS_SERVICE_URL=http://127.0.0.1:8102"
if "%CATALOG_SERVICE_URL%"==""       set "CATALOG_SERVICE_URL=http://127.0.0.1:8103"
if "%MAIN_PROCESS_SERVICE_URL%"==""  set "MAIN_PROCESS_SERVICE_URL=http://127.0.0.1:8104"
if "%DOCUMENTS_SERVICE_URL%"==""     set "DOCUMENTS_SERVICE_URL=http://127.0.0.1:8105"
if "%QUERIES_SERVICE_URL%"==""       set "QUERIES_SERVICE_URL=http://127.0.0.1:8107"
if "%REPORTS_SERVICE_URL%"==""       set "REPORTS_SERVICE_URL=http://127.0.0.1:8108"
if "%ALGORITHMS_SERVICE_URL%"==""    set "ALGORITHMS_SERVICE_URL=http://127.0.0.1:8109"

entorno\Scripts\python.exe app.py
if errorlevel 1 pause
