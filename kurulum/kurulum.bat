@echo off
REM Memecoin Radar - Windows kurulumu. Cift tiklayin (kurulum.ps1 ile ayni klasorde olmali).
REM NOT: Windowsta henuz denenmedi.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kurulum.ps1"
if errorlevel 1 pause
