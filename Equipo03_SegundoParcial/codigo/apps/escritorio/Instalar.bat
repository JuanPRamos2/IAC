@echo off
REM Bienestar Nexum - Escritorio (XML). Se corre una sola vez.
setlocal
cd /d "%~dp0"

echo.
echo  Bienestar Nexum - Escritorio
echo  ============================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo  FALTA PYTHON.
        echo  Descargalo de https://www.python.org/downloads/
        echo  Al instalarlo, marca la casilla "Add python.exe to PATH".
        echo.
        pause
        exit /b 1
    )
)

echo  Python encontrado. Preparando el entorno...
echo.

%PY% -m venv entorno
if errorlevel 1 (
    echo  No se pudo crear el entorno.
    pause
    exit /b 1
)

echo  Instalando lxml...
entorno\Scripts\python.exe -m pip install --quiet --upgrade pip
entorno\Scripts\python.exe -m pip install --quiet lxml
if errorlevel 1 (
    echo  No se pudo instalar lxml. Revisa la conexion.
    pause
    exit /b 1
)

echo.
echo  LISTO. Para abrir el programa, usa Iniciar.bat
echo.
pause
