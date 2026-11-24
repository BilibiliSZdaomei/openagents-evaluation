@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0manage.py" (
  echo Place this file next to manage.py and Start.cmd in the OpenAgents evaluation checkout.
  pause
  exit /b 1
)
if not exist "%~dp0Start.cmd" (
  echo Missing Start.cmd in the OpenAgents evaluation checkout.
  pause
  exit /b 1
)
if not "%~1"=="" goto supplied
if not exist "%~dp0openagents-linux-amd64-images.tar.gz" (
  echo Place the image archive and SHA256SUMS next to this file, or drag the image archive onto it.
  pause
  exit /b 1
)
"%~dp0Start.cmd" images "%~dp0openagents-linux-amd64-images.tar.gz"
:supplied
"%~dp0Start.cmd" images "%~f1"
