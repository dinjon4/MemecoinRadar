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

start "Memecoin Radar - Tarama" ".venv\Scripts\python.exe" main.py
REM Panel "headless" calisir: Streamlit'in ilk acilista sordugu e-posta sorusu cikmaz. Tarayiciyi biz acariz.
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8501"
REM Panel guncelleme yaptiktan sonra 75 koduyla kapanir; o zaman yeniden acilir.
:panel
".venv\Scripts\python.exe" -m streamlit run panel.py --server.headless true
if %ERRORLEVEL%==75 (
    echo Guncelleme yapildi, panel yeniden baslatiliyor...
    goto panel
)
pause
