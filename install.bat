@echo off
echo ========================================
echo   Installation des dependances
echo ========================================
echo.
cd backend
echo Installation backend...
call npm install
echo.
echo ========================================
echo   Installation terminee !
echo ========================================
echo.
echo Pour demarrer l'application :
echo   1. Double-cliquez sur start.bat
echo   2. Ouvrez http://localhost:3000 dans votre navigateur
echo.
pause
