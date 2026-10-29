@echo off
rem 一键流水线：env-check -> scan -> import -> validate -> publish
chcp 65001 >nul
set SRC=%~1
if "%SRC%"=="" (
    if exist "D:\IMAGE\10.28" set SRC=D:\IMAGE\10.28
    if exist "D:\IMAGE\待发布" set SRC=D:\IMAGE\待发布
    if exist "E:\测试" set SRC=E:\测试
)
if "%SRC%"=="" (
    echo [错误] 请指定素材目录，例如: run.bat D:\IMAGE\10.28
    exit /b 1
)
shift
if "%PYTHON%"=="" set PYTHON=python
echo [Dewu Pipeline] 使用素材目录: %SRC%
%PYTHON% "%~dp0scripts\dewu_tool.py" run --src "%SRC%" --config "%~dp0work\posts.json" --reuse-config %1 %2 %3 %4
