@echo off
REM II-Agent Newsletter Scheduled Tasks Setup
REM Run this script as Administrator to set up daily newsletters

echo Setting up II-Agent scheduled tasks...
echo.

REM Delete existing tasks if they exist
schtasks /delete /tn "II-Agent Net Worth Newsletter" /f 2>nul
schtasks /delete /tn "II-Agent Market Newsletter" /f 2>nul
schtasks /delete /tn "II-Agent WHOOP Dashboard" /f 2>nul

REM Create Net Worth Newsletter task (7:00 AM daily)
echo Creating Net Worth Newsletter task (7:00 AM)...
schtasks /create /tn "II-Agent Net Worth Newsletter" /tr "C:\Users\user\ii-agent\src\ii_skills\networth_newsletter\run_networth.bat" /sc daily /st 07:00 /ru "%USERNAME%" /rl HIGHEST

REM Create Market Newsletter task (7:15 AM daily)
echo Creating Market Newsletter task (7:15 AM)...
schtasks /create /tn "II-Agent Market Newsletter" /tr "C:\Users\user\ii-agent\src\ii_skills\market_newsletter\run_newsletter.bat" /sc daily /st 07:15 /ru "%USERNAME%" /rl HIGHEST

REM Create WHOOP Dashboard task (7:30 AM daily)
echo Creating WHOOP Dashboard task (7:30 AM)...
schtasks /create /tn "II-Agent WHOOP Dashboard" /tr "C:\Users\user\ii-agent\src\ii_skills\health_dashboard\run_whoop.bat" /sc daily /st 07:30 /ru "%USERNAME%" /rl HIGHEST

echo.
echo Scheduled tasks created successfully!
echo.
echo Task Schedule:
echo   - Net Worth Newsletter: 7:00 AM daily
echo   - Market Newsletter: 7:15 AM daily
echo   - WHOOP Dashboard: 7:30 AM daily
echo.
echo To verify: schtasks /query /tn "II-Agent*"
pause
