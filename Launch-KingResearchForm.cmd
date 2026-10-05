@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%data\raw\legacy-replay\.venv\Scripts\python.exe"
set "BUNDLE=%ROOT%data\raw\king-benchmark\king-absolute-error-serving-20261006-v1"

if not exist "%ROOT%data\raw\legacy-replay\.venv\Scripts\python.exe" goto :missing_python
if not exist "%ROOT%data\raw\king-benchmark\king-absolute-error-serving-20261006-v1\manifest.json" goto :missing_bundle

set "PYTHONPATH=%ROOT%;%ROOT%src"
"%PYTHON_EXE%" -m scripts.king_research_form ^
  --bundle "%BUNDLE%" ^
  --manifest-sha256 50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d
exit /b %ERRORLEVEL%

:missing_python
echo King research form unavailable: pinned Python environment is missing. 1>&2
exit /b 2

:missing_bundle
echo King research form unavailable: verified model bundle is missing. 1>&2
exit /b 2
