@echo off
title Bot de Cargas Telegram (@cargasespanabot) - Siempre Activo
cd /d "%~dp0"
echo ====================================================
echo  Bot de Cargas de Telegram (Modo Siempre Operativo)
echo ====================================================
:bucle
python bot.py
echo.
echo [Aviso] El bot se ha cerrado. Reiniciando en 3 segundos...
timeout /t 3 /nobreak >nul
goto bucle
