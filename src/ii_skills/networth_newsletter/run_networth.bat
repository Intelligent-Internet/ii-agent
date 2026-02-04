@echo off
REM Daily Net Worth Newsletter Runner
REM This script is designed to be run by Windows Task Scheduler

cd /d "C:\Users\user\ii-agent\src\ii_skills\networth_newsletter"
python networth.py >> networth.log 2>&1
