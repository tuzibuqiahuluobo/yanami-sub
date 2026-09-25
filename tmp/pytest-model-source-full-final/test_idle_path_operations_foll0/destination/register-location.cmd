@echo off
rem Register this folder as FineSub's data directory.
rem After moving it somewhere else in Explorer, double-click this once.
setlocal
set "STORE=%~dp0"
if not exist "%STORE%.finesub-store.json" (
    echo This folder is not a FineSub data directory.>&2
    pause
    exit /b 1
)
set "RECORD=%LOCALAPPDATA%\FineSub"
if not exist "%RECORD%" mkdir "%RECORD%"
rem Drop the trailing backslash: it would escape the closing quote in the JSON.
set "STORE=%STORE:~0,-1%"
set "STORE=%STORE:\=\\%"
> "%RECORD%\locations.json" echo {"schemaVersion": 1, "bigData": "%STORE%"}
echo Registered: %~dp0
pause
