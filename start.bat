@echo off
chcp 65001 >nul
title VisionPay Agent Platform - 一键启动

echo ========================================
echo   VisionPay Agent Platform 一键启动
echo ========================================
echo.

REM 启动 Docker 基础服务
echo [1/3] 启动 Docker 基础服务 (PostgreSQL, Redis, MinIO)...
docker compose up -d postgres redis minio
if errorlevel 1 (
    echo 错误: Docker 服务启动失败，请确认 Docker Desktop 正在运行
    pause
    exit /b 1
)

REM 启动后端
echo [2/3] 启动后端 (FastAPI @ 8000)...
if not exist backend\.venv (
    echo 错误: backend\.venv 不存在，请先运行 setup.bat 或手动创建虚拟环境
    pause
    exit /b 1
)
start "VisionPay Backend" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

REM 启动前端
echo [3/3] 启动前端 (Vite @ 5173)...
if not exist frontend\node_modules (
    echo 警告: frontend\node_modules 不存在，正在安装依赖...
    cd /d %~dp0frontend
    npm install
    if errorlevel 1 (
        echo 错误: 前端依赖安装失败
        pause
        exit /b 1
    )
    cd /d %~dp0
)
start "VisionPay Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo   服务已启动
echo ========================================
echo.
echo   后端 API:     http://127.0.0.1:8000
echo   前端页面:     http://127.0.0.1:5173
echo   Swagger 文档: http://127.0.0.1:8000/docs
echo.
echo   后端和前端分别在新窗口中运行，
echo   关闭对应窗口即可停止服务。
echo.
pause
