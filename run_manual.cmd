@echo off
rem Manda videos pro bot (sequencia). Dispare com:
rem   schtasks /run /tn CortesRunManual
cd /d "C:\Users\Administrator\Documents\cortes"
python -X utf8 cortes.py run https://youtu.be/7vqxsEBg1Cc --publish > "logs\run_manual.log" 2>&1
python -X utf8 cortes.py run https://youtu.be/aVh0QMKKK6M --publish >> "logs\run_manual.log" 2>&1
