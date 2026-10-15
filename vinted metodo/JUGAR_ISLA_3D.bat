@echo off
title Isla 3D - Supervivencia Estilo Raft
echo ========================================================
echo    Iniciando Servidor de Juego: RAFT ISLAND 3D
echo ========================================================
echo Abriendo en el navegador predeterminado...
cd /d "%~dp0"
start "" "http://localhost:8080/raft_island_game/"
python -m http.server 8080
pause
