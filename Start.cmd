@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
set "portable=.tools\python-3.14.10\python.exe"
set "bundle=python-3.14.10-embed-amd64.zip"
set "entry=manage.py"
set "defaultArgs=up"
if exist "%portable%" goto portable
if exist "%bundle%" goto unpack
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys; sys.exit(sys.version_info[:2] < (3,10))" >nul 2>&1
  if not errorlevel 1 goto launcher
)
where python >nul 2>&1
if not errorlevel 1 (
  python -c "import sys; sys.exit(sys.version_info[:2] < (3,10))" >nul 2>&1
  if not errorlevel 1 goto systempython
)
echo 首次启动需要 Python。从本仓库 GitHub Release 下载 %bundle%，放在 Start.cmd 旁边，再双击一次。
echo 下载页 https://github.com/BilibiliSZdaomei/openagents-evaluation/releases/tag/runtime-linux-amd64-20261124
set "status=1"
goto done
:unpack
powershell.exe -NoProfile -Command "$env:PSModulePath=(Join-Path $PSHOME 'Modules')+';'+$env:PSModulePath; $ErrorActionPreference='Stop'; $part=$env:bundle; if ((Get-FileHash -Algorithm SHA256 -LiteralPath $part).Hash -ne '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159') {throw 'Python archive checksum mismatch'}; $dir='.tools\python-3.14.10'; $null=New-Item -Path '.tools' -ItemType Directory -Force; $tmp=Join-Path '.tools' ('unpack-'+[Guid]::NewGuid()); Expand-Archive -LiteralPath $part -DestinationPath $tmp; if (!(Test-Path -LiteralPath (Join-Path $tmp 'python.exe'))) {throw 'Incomplete Python archive'}; Move-Item -LiteralPath $tmp -Destination $dir"
if errorlevel 1 goto error
:portable
if "%~1"=="" ("%portable%" "%entry%" %defaultArgs%) else ("%portable%" "%entry%" %*)
goto result
:launcher
if "%~1"=="" (py -3 "%entry%" %defaultArgs%) else (py -3 "%entry%" %*)
goto result
:systempython
if "%~1"=="" (python "%entry%" %defaultArgs%) else (python "%entry%" %*)
:result
set "status=%errorlevel%"
goto done
:error
set "status=1"
:done
popd
if not "%status%"=="0" if "%~1"=="" pause
exit /b %status%
