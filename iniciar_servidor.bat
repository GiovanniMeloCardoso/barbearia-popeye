@echo off
chcp 65001 >nul
title Servidor Django - Barbearia Popeye
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    if not exist "..\.venv\Scripts\activate.bat" (
        echo [INFO] Ambiente virtual não detectado. Iniciando configuração inicial...
        if exist "configurar_novo_pc.bat" (
            call "configurar_novo_pc.bat"
        ) else (
            python -m venv venv
            call "venv\Scripts\activate.bat"
            pip install -r requirements.txt
        )
    )
)

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else if exist "..\.venv\Scripts\activate.bat" (
    call "..\.venv\Scripts\activate.bat"
)

echo.
echo ========================================================
echo       INICIANDO SERVIDOR DJANGO - BARBEARIA POPEYE
echo       Acesse no navegador: http://localhost:8000
echo ========================================================
echo.

python manage.py runserver
pause
