@echo off
cd /d "%~dp0"

echo [1/3] Building frontend...
cd frontend
call npm install --silent
call npm run build
if errorlevel 1 (
    echo ERROR: Frontend build failed
    pause
    exit /b 1
)
cd ..
echo Done.

echo [2/3] Installing dependencies...
py -3.11 -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)
echo Done.

echo [3/3] Building .exe...
py -3.11 -m PyInstaller doc_reviewer.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed
    pause
    exit /b 1
)

echo.
echo Build complete: dist\doc-reviewer.exe
echo.
pause
