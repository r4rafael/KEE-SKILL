@echo off
chcp 65001 >nul
title KEE-SKILL Installer
echo ============================================
echo  KEE - Knowledge Extractor Engine Installer
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado! Instale Python 3.8+
    pause
    exit /b 1
)
echo [OK] Python encontrado

echo.
echo Instalando dependencias Python...
pip install -r "%~dp0requirements.txt" -q
echo [OK] Dependencias instaladas

deno --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [AVISO] Deno nao encontrado. Instale de https://deno.com
) else (
    echo [OK] Deno encontrado
)

echo.
echo ============================================
echo  Instalacao concluida!
echo.
echo  Para usar:  python src/baixar-knowhow.py
echo  Ou link:    python src/baixar-knowhow.py "URL"
echo ============================================
pause