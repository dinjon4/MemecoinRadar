@echo off
REM Memecoin Radar - Windows baslatici. Cift tiklayin.
REM Tarama servisini ayri bir pencerede, paneli bu pencerede baslatir.
REM Kapatmak icin iki pencereyi de kapatin (veya Ctrl+C).

chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Sanal ortam bulunamadi, kuruluyor ^(ilk seferde birkac dakika surebilir^)...
    py -3 -m venv .venv || python -m venv .venv || (echo Python bulunamadi. python.org'dan Python kurun. & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Paketler kurulamadi. & pause & exit /b 1)
)

if not exist ".env" (
    echo UYARI: .env dosyasi yok. Telegram mesajlari gonderilemez. .env.example dosyasini .env olarak kopyalayip doldurun.
)

start "Memecoin Radar - Tarama" ".venv\Scripts\python.exe" main.py
".venv\Scripts\python.exe" -m streamlit run panel.py
pause
