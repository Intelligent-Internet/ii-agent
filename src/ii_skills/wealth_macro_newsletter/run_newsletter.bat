@echo off
REM Wealth Macro Daily Newsletter Runner
REM =====================================
REM Scheduled to run daily at 7:00 AM

cd /d C:\Users\user\ii-agent
python src\ii_skills\wealth_macro_newsletter\generate_newsletter.py --send

REM Log the run
echo [%date% %time%] Wealth Macro Newsletter executed >> logs\wealth_macro_newsletter.log
