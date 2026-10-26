@echo off
rem ============================================================
rem  SamaImmo - demarrage Windows
rem  1) Extraire TOUT le zip (clic droit > Extraire tout)
rem  2) Double-cliquer sur start.bat
rem ============================================================
cd /d "%~dp0"
title SamaImmo

rem ---- verifie que le projet est bien extrait (pas lance depuis le zip) ----
if not exist "requirements.txt" goto err_extrait
if not exist "app\main.py" goto err_extrait

rem ---- 1) trouver Python (commande python, sinon lanceur py) ----
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  py --version >nul 2>&1
  if not errorlevel 1 set "PY=py"
)
if defined PY goto py_ok
echo.
echo [ERREUR] Python est introuvable.
echo.
echo Installez Python 3.10 ou plus recent depuis https://www.python.org/downloads/
echo en cochant la case "Add Python to PATH" a l'installation, puis relancez start.bat
echo.
pause
exit /b 1
:py_ok

rem ---- 2) verifier la version (3.10 minimum) ----
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto err_version
for /f "tokens=2" %%v in ('%PY% --version 2^>^&1') do echo Python detecte : %%v

rem ---- 3) environnement virtuel + dependances (une seule fois) ----
if exist ".venv\Scripts\python.exe" goto env_ok
echo.
echo Premier lancement : installation des dependances (1 a 2 minutes)...
echo Laissez cette fenetre ouverte jusqu'a la fin.
echo.
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto err_venv
call ".venv\Scripts\python" -m pip install --upgrade pip
call ".venv\Scripts\python" -m pip install -r requirements.txt
if errorlevel 1 goto err_pip
echo.
echo Installation terminee.
:env_ok

rem ---- 4) fichier .env ----
if exist ".env" goto envf_ok
copy .env.example .env >nul
:envf_ok

rem ---- 5) donnees de demonstration (au premier lancement seulement) ----
if exist "data\app.db" goto demo_ok
echo.
set "REP="
set /p "REP=Charger les donnees de demonstration (2 proprietaires, 5 biens, quittances) ? (O/N) : "
if /I not "%REP%"=="O" goto demo_ok
call ".venv\Scripts\python" scripts\seed_demo.py
:demo_ok

rem ---- 6) choix automatique d'un port libre ----
set "PORT=8000"
set "ESSAIS=0"
:port_suivant
netstat -ano 2>nul | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 goto port_libre
echo.
echo   Le port %PORT% est deja occupe par une autre application, essai du suivant...
set /A ESSAIS=ESSAIS+1
if %ESSAIS% GEQ 20 goto err_port
set /A PORT=PORT+1
goto port_suivant
:port_libre
set "BASE_URL=http://localhost:%PORT%"

echo.
echo   =====================================================
echo.
echo     SamaImmo demarre sur :  http://localhost:%PORT%
echo.
echo     Compte de demo :  +221 770 000 000
echo     Code de connexion : affiche a l'ecran apres l'envoi
echo.
echo     Pour arreter : Ctrl+C ou fermez cette fenetre
echo.
echo   =====================================================
echo.
".venv\Scripts\python" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%

echo.
echo [Le serveur est arrete.]
pause
exit /b 0

:err_extrait
echo.
echo [ERREUR] Fichiers du projet introuvables.
echo Vous avez probablement lance start.bat depuis l'archive ZIP sans l'extraire.
echo Extrayez TOUT le zip (clic droit ^> Extraire tout) puis relancez start.bat.
echo.
pause
exit /b 1

:err_version
echo.
echo [ERREUR] Python 3.10 ou plus recent est requis. Votre version :
%PY% --version
echo Telechargez la derniere version sur https://www.python.org/downloads/
echo.
pause
exit /b 1

:err_venv
echo.
echo [ERREUR] La creation de l'environnement virtuel a echoue.
echo.
pause
exit /b 1

:err_pip
echo.
echo [ERREUR] L'installation des dependances a echoue.
echo Verifiez votre connexion internet puis relancez start.bat.
echo.
pause
exit /b 1

:err_port
echo.
echo [ERREUR] Aucun port libre entre 8000 et 8019.
echo.
pause
exit /b 1
