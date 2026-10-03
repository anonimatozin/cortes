@echo off
cd /d "C:\Users\Administrator\Documents\cortes"
echo ==== %date% %time% tentativa ==== >> "logs\publish_auto.log"
"C:\Program Files\Python312\python.exe" cortes.py publish --privacy public >> "logs\publish_auto.log" 2>&1
echo ==== %date% %time% fim ==== >> "logs\publish_auto.log"
