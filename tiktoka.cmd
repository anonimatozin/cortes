@echo off
cd /d "C:\Users\Administrator\Documents\cortes"
echo ==== %date% %time% tentativa tiktok ==== >> "logs\tiktok_auto.log"
python cortes.py publish --platform tiktok >> "logs\tiktok_auto.log" 2>&1
echo ==== %date% %time% fim ==== >> "logs\tiktok_auto.log"
