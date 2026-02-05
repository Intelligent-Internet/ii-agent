@echo off
REM Daily Market Newsletter Runner
REM This script is designed to be run by Windows Task Scheduler
REM Auto-restores config from OneDrive backup before each run

set BACKUP="C:\Users\user\OneDrive\Desktop\RJ\II-Agent Credentials\configs\market_config.py"
set TARGET="C:\Users\user\ii-agent\src\ii_skills\market_newsletter\config.py"

if exist %BACKUP% (
    copy /Y %BACKUP% %TARGET% >nul 2>&1
)

cd /d "C:\Users\user\ii-agent\src\ii_skills\market_newsletter"
python newsletter.py >> newsletter.log 2>&1
