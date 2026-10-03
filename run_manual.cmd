@echo off
rem Manda um video pro bot. Edite a URL abaixo e rode:
rem   schtasks /run /tn CortesRunManual
cd /d "C:\Users\Administrator\Documents\cortes"
python -X utf8 cortes.py run https://youtu.be/URL_AQUI --publish > "logs\run_manual.log" 2>&1
