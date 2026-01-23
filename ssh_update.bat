@echo off
echo Mashkov.Rest | ssh -o StrictHostKeyChecking=no root@155.212.164.61 "cd /opt/telegram-bot && pwd && whoami && sudo -u botuser git pull origin master && sudo supervisorctl restart telegram-bot-group"
