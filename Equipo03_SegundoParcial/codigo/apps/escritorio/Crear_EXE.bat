@echo off
REM Opcional. Genera dist\BienestarNexumEscritorio.exe despues de Instalar.bat.
setlocal
cd /d "%~dp0"

if not exist "entorno\Scripts\python.exe" (
    echo  Corre primero Instalar.bat
    pause
    exit /b 1
)

echo  Instalando PyInstaller...
entorno\Scripts\python.exe -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo  Fallo la instalacion.
    pause
    exit /b 1
)

echo  Empaquetando. Tarda unos minutos...
entorno\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed ^
    --name BienestarNexumEscritorio ^
    --add-data "..\..\contratos\xml;contratos_xml" ^
    exe_main.py

echo.
if exist "dist\BienestarNexumEscritorio.exe" (
    echo  LISTO: dist\BienestarNexumEscritorio.exe
) else (
    echo  No se genero el ejecutable. Revisa los mensajes de arriba.
)
echo.
pause
