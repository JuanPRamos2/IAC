@echo off
set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%BASH%" set "BASH=%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
if not exist "%BASH%" (
  echo Git Bash no esta instalado. Usa el guion de PowerShell:
  echo powershell -ExecutionPolicy Bypass -File "%~dp0ensayo_fallos_presentacion.ps1"
  exit /b 1
)
"%BASH%" "%~dp0ensayo_fallos_presentacion.sh"
