@echo off
setlocal
if exist "%~dp0Wuhan_Study.mxd" (
  start "" "%~dp0Wuhan_Study.mxd"
  exit /b 0
)
if not exist "%~dp0Scripts\initialize_arcmap105.py" (
  echo Extract the complete ZIP before opening the map.
  pause
  exit /b 1
)
set "ARC_PY="
for %%D in (C D E F) do (
  if not defined ARC_PY if exist "%%D:\Python27\ArcGIS10.5\python.exe" set "ARC_PY=%%D:\Python27\ArcGIS10.5\python.exe"
)
if not defined ARC_PY (
  echo Please select the Python executable installed with ArcGIS Desktop 10.5.
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select ArcGIS Desktop Python executable'; $d.Filter='Python executable (python.exe)|python.exe'; if($d.ShowDialog() -eq 'OK'){Write-Output $d.FileName}"`) do set "ARC_PY=%%P"
)
if not defined ARC_PY (
  echo ArcGIS Python was not selected. You can still add Data\Wuhan_Study.gdb and Views in ArcMap.
  pause
  exit /b 1
)
"%ARC_PY%" "%~dp0Scripts\initialize_arcmap105.py" --root "%~dp0." --package --open
if errorlevel 1 pause
endlocal
