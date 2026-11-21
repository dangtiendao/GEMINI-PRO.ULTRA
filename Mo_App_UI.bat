@echo off
chcp 65001 >nul
title Google AI Pro / Ultra - App UI
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
start "" pythonw app_ui.py || python app_ui.py
