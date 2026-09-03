@echo off
chcp 65001 >nul
echo ==========================================
echo   Tonuino SD-Manager - EXE erstellen
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
echo Erstelle EXE-Datei...
python build_exe.py
if errorlevel 1 (
    echo FEHLER beim Erstellen der EXE!
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   ERFOLG!
echo ==========================================
echo.
echo Die EXE-Datei befindet sich jetzt im "dist"-Ordner.
echo.
pause
