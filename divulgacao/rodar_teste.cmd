@echo off
chcp 65001 >nul
setlocal
rem Roda o teste de ponta a ponta do modulo divulgacao (sem rede, sem chave).
rem A saida vai para %TEMP%\divulgacao_teste e nada do projeto real e tocado.
cd /d "%~dp0\.."
python -m divulgacao.teste.teste_ponta_a_ponta
echo.
set RC=%ERRORLEVEL%
if %RC%==0 (echo TESTE OK) else (echo TESTE FALHOU - codigo %RC%)
pause
exit /b %RC%
