@echo off
title WEIS Web — Wollam Estimating Intelligence System
cd /d "%~dp0"
call "%~dp0.venv\Scripts\activate.bat"
streamlit run app/web.py
pause
