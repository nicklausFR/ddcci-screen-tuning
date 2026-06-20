@echo off

REM Build
pyinstaller main.py --onefile --windowed

REM Renommage avec écrasement
move /Y dist\main.exe dist\ScreenTuning.exe

REM Nettoyage build PyInstaller
rmdir /S /Q build
