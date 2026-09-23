@echo off
rem Builds ooz.dll (open-source Kraken decoder, GPL-3.0) with the latest Visual Studio C++ tools.
setlocal
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -property installationPath`) do set "VS=%%i"
if not defined VS (echo Visual Studio with C++ tools not found & exit /b 1)
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
rem kraken.cpp also carries the ooz command-line tool, which needs sys/stat.h
cl /nologo /O2 /EHsc /MT /LD /DNDEBUG /w /FIsys/types.h /FIsys/stat.h "%~dp0kraken.cpp" "%~dp0ooz_export.cpp" /Fe:"%~dp0ooz.dll" /Fo:"%TEMP%\\" /link /NOLOGO || exit /b 1
del /q "%~dp0ooz.lib" "%~dp0ooz.exp" 2>nul
echo built %~dp0ooz.dll
