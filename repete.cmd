@echo off
cd /d "C:\Users\Administrator\Documents\cortes"
setlocal EnableDelayedExpansion
set /a tentativa=0

:loop
set /a tentativa+=1
if exist "logs\PARA" (
  echo ==== %date% %time% parado pelo usuario ==== >> "logs\publish_retry.log"
  exit /b
)
if !tentativa! GTR 16 (
  echo ==== %date% %time% fim das 16 tentativas ==== >> "logs\publish_retry.log"
  exit /b
)
echo ==== tentativa !tentativa! %date% %time% ==== >> "logs\publish_retry.log"
python cortes.py publish --privacy public >> "logs\publish_retry.log" 2>&1
python -c "import json,sys;sys.exit(0 if all(c.get('youtube') for j in json.load(open('queue/jobs.json',encoding='utf-8'))['jobs'] for c in j.get('clips',[]) if __import__('pathlib').Path(c['path']).exists()) else 1)" >> "logs\publish_retry.log" 2>&1
if !errorlevel! EQU 0 (
  echo ==== %date% %time% tudo publicado, saindo ==== >> "logs\publish_retry.log"
  exit /b
)
echo    ainda falta corte, tentando de novo em 45 min >> "logs\publish_retry.log"
timeout /t 2700 /nobreak >nul
goto loop
