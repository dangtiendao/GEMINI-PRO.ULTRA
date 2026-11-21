@echo off
chcp 65001 >nul
title Ultra 30TB Giam 90% ($19.99/thang x 3M)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ============================================
echo   Google AI Ultra 30TB - Giam 90%% (introprice)
echo   SKU: g1.ai.ultra.3months_ip_90p.acq
echo   Gia: $19.99/thang x 3 thang (sau do $199.99/P1M)
echo ============================================
python ultra0.py --account "current@device" --no-add --force --plan ultra30_90p
echo.
pause
