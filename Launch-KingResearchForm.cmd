@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%data\raw\legacy-replay\.venv\Scripts\python.exe"
set "BUNDLE=%ROOT%data\raw\king-benchmark\king-validation-20261004-v1"
set "FHFA_SOURCE=%ROOT%data\raw\fhfa\hpi_po_metro_2026-10-05.txt"

if not exist "%ROOT%data\raw\legacy-replay\.venv\Scripts\python.exe" goto :missing_python
if not exist "%ROOT%data\raw\king-benchmark\king-validation-20261004-v1\manifest.json" goto :missing_bundle
if not exist "%ROOT%data\raw\fhfa\hpi_po_metro_2026-10-05.txt" goto :missing_fhfa

set "PYTHONPATH=%ROOT%;%ROOT%src"
"%PYTHON_EXE%" -m scripts.king_research_form ^
  --bundle "%BUNDLE%" ^
  --manifest-sha256 32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9 ^
  --fhfa-source "%FHFA_SOURCE%"
exit /b %ERRORLEVEL%

:missing_python
echo King research form unavailable: pinned Python environment is missing. 1>&2
exit /b 2

:missing_bundle
echo King research form unavailable: verified model bundle is missing. 1>&2
exit /b 2

:missing_fhfa
echo King research form unavailable: pinned FHFA source snapshot is missing. 1>&2
exit /b 2
