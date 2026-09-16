@echo off
chcp 65001 >nul
echo ==========================================
echo   Tonuino-Manager - Programmdatei und Installer erstellen
echo ==========================================
echo.

echo Ueberpruefe Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden!
    echo Bitte installiere Python 3.10 oder neuer.
    pause
    exit /b 1
)

echo.
echo Installiere Abhaengigkeiten...
pip install -r requirements.txt
if errorlevel 1 (
    echo FEHLER bei der Installation!
    pause
    exit /b 1
)

echo.
echo Erstelle Programmdatei und Installer...
python build_package.py
if errorlevel 1 (
    echo FEHLER beim Erstellen!
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   ERFOLG!
echo ==========================================
echo.
echo Programmdatei und Installer befinden sich jetzt im "dist"-Ordner.
echo.
pause
