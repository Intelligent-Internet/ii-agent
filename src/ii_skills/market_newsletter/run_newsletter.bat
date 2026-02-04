@echo off
REM Daily Market Newsletter Runner
REM This script is designed to be run by Windows Task Scheduler

cd /d "C:\Users\user\ii-agent\src\ii_skills\market_newsletter"
python newsletter.py >> newsletter.log 2>&1
