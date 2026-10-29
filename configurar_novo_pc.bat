@echo off
chcp 65001 >nul
title Configuração do Ambiente - Barbearia Popeye
cd /d "%~dp0"

echo ========================================================
echo       CONFIGURANDO PROJETO NO NOVO COMPUTADOR
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] Python não foi encontrado no sistema!
    echo Por favor, instale o Python (3.10 ou superior) e marque a opção:
    echo 'Add Python to PATH' durante a instalação.
    echo Baixe em: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Verificando / Criando ambiente virtual (venv)...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
    echo Ambiente virtual criado com sucesso!
) else (
    echo Ambiente virtual já existente.
)

echo.
echo [2/3] Instalando dependências do requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

echo.
echo [3/3] Verificando integridade do Django...
python manage.py check

echo.
echo ========================================================
echo   CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!
echo   Para iniciar o sistema, basta executar: iniciar_servidor.bat
echo ========================================================
pause
