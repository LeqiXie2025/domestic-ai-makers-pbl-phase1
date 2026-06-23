@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" pythonw wechat_agent_app.py
echo WeChat Agent window launched.
