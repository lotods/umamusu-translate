@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION

REM Set workdir correctly when called from scripts dir
FOR %%I IN (.) DO SET parent=%%~nxI
IF %parent% EQU scripts (
    CD ../../..
)

REM Check for existing install
IF EXIST "UmaTL" (
    SET name=UmaTL
)
IF EXIST "umamusu-translate" (
    SET name=umamusu-translate
)
IF DEFINED name (
    CALL :update
) ELSE (
    CALL :install
)
PAUSE
EXIT /B

REM FUNCTIONS

:install
CALL :mingit
CALL :initgit
MOVE uma-temp-mingit UmaTL\.mingit
CD UmaTL
CALL patch.bat install
EXIT /B 0

:update
SET /P reinstall=Existing UmaTL found. What do you want to do? [u]pdate, [r]einstall, [e]xit:
IF /I !reinstall! EQU r (
    RMDIR /S /Q %name%
    CALL :install
) ELSE IF /I !reinstall! EQU u (
    CALL patch.bat install
    EXIT /B
) ELSE (
    ECHO No actions required, exiting.
)
EXIT /B

:mingit
ECHO Installing MinGit ^(https://github.com/git-for-windows/git/releases^)...
IF EXIST "uma-temp-mingit\mingw64" (
    EXIT /B 0
)
MKDIR uma-temp-mingit
IF NOT EXIST "uma-temp-mingit.zip" (
    curl -L -o uma-temp-mingit.zip "https://github.com/git-for-windows/git/releases/download/v2.38.1.windows.1/MinGit-2.38.1-64-bit.zip"
)
tar -xf uma-temp-mingit.zip -C uma-temp-mingit
DEL uma-temp-mingit.zip
EXIT /B 0

:initgit
SET mingit=uma-temp-mingit\mingw64\bin\git.exe
REM Ensure CA certs for temp dir
%mingit% config --system http.sslcainfo uma-temp-mingit\mingw64\ssl\certs\ca-bundle.crt
REM Ensure this setting is set correctly
%mingit% config --system credential.helper manager-core
ECHO Downloading UmaTL ^(initializing git repo^)...
%mingit% clone https://github.com/noccu/umamusu-translate.git UmaTL
REM Ensure CA certs are found. Set mingit's default config to use its own certs (why does it not?)
%mingit% config --system http.sslcainfo .mingit\mingw64\ssl\certs\ca-bundle.crt
EXIT /B 0