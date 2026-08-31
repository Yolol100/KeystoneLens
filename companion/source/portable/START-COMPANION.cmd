@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%runtime\python.exe"
set "PYTHONW=%ROOT%runtime\pythonw.exe"
set "CHECKLOG=%TEMP%\keystonelens-portable-check.txt"

if not exist "%PYTHON%" (
  echo KeystoneLens Portable runtime ontbreekt.
  echo Pak de volledige ZIP opnieuw uit en verplaats niet alleen dit bestand.
  pause
  exit /b 1
)

if not exist "%PYTHONW%" (
  echo KeystoneLens Portable runtime is onvolledig.
  echo Pak de volledige ZIP opnieuw uit.
  pause
  exit /b 1
)

"%PYTHON%" -I "%ROOT%portable_launcher.py" --verify > "%CHECKLOG%" 2>&1
if errorlevel 1 (
  echo KeystoneLens Portable kon de lokale runtime niet laden.
  echo.
  type "%CHECKLOG%"
  echo.
  echo Diagnosebestand: %CHECKLOG%
  pause
  exit /b 1
)

del /q "%CHECKLOG%" >nul 2>&1
start "" /D "%ROOT%" "%PYTHONW%" -I "%ROOT%portable_launcher.py"
exit /b 0
