@echo off
REM Daily WHOOP Health Dashboard Runner
REM This script is designed to be run by Windows Task Scheduler
REM Auto-restores config from OneDrive backup before each run

set BACKUP="C:\Users\user\OneDrive\Desktop\RJ\II-Agent Credentials\configs\whoop_config.py"
set TARGET="C:\Users\user\ii-agent\src\ii_skills\health_dashboard\config.py"

if exist %BACKUP% (
    copy /Y %BACKUP% %TARGET% >nul 2>&1
)

cd /d "C:\Users\user\ii-agent\src\ii_skills\health_dashboard"
python whoop_newsletter.py >> whoop.log 2>&1
