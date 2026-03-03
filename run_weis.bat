@echo off
title WEIS - Wollam Estimating Intelligence System
cd /d "%~dp0"
call "%~dp0.venv\Scripts\activate.bat"
python -m app.main
pause
