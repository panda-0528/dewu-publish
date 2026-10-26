@echo off
rem 一键流水线：env-check -> scan -> import -> gen-copy(GLM) -> validate -> publish
rem 用法: set GLM_API_KEY=xxx ^& run.bat 素材目录 [额外参数]
chcp 65001 >nul
if "%~1"=="" (echo 用法: run.bat 素材目录 [额外参数] & exit /b 1)
set SRC=%~1
shift
if "%PYTHON%"=="" set PYTHON=python
%PYTHON% "%~dp0scripts\dewu_tool.py" run --src "%SRC%" --config "%~dp0work\posts.json" %1 %2 %3 %4
