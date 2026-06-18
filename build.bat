@echo off
cd /d "%~dp0"

echo [1/3] Building frontend...
cd frontend

:: Передаём дату сборки в Vite через переменную среды
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set VITE_BUILD_DATE=%DT:~6,2%.%DT:~4,2%.%DT:~0,4%

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

echo Installing Playwright browsers...
py -3.11 -m playwright install chromium
if errorlevel 1 (
    echo ERROR: Playwright browser install failed
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
