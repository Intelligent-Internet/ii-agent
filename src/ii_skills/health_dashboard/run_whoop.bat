@echo off
REM Daily WHOOP Health Dashboard Runner
REM This script is designed to be run by Windows Task Scheduler

cd /d "C:\Users\user\ii-agent-repo\src\ii_skills\health_dashboard"
python whoop_newsletter.py >> whoop.log 2>&1
