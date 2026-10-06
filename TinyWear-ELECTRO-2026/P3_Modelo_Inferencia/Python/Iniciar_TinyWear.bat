@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto usar_python
py -3 Interfaz_TinyWear_WIFI.py %*
goto finalizar
:usar_python
python Interfaz_TinyWear_WIFI.py %*
:finalizar
if errorlevel 1 (
  echo.
  echo Revisar el mensaje anterior. Se requiere Python 3.10 o posterior con Tkinter.
  pause
)
endlocal
