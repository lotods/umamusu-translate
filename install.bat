@ECHO OFF
SETLOCAL
CALL :mingit
CALL run.bat install
EXIT /B

REM FUNCTIONS

:mingit
IF NOT EXIST ".mingit" (
    ECHO Installing MinGit ^(https://github.com/git-for-windows/git/releases^)...
    mkdir .mingit
    curl -L -o mingit.zip "https://github.com/git-for-windows/git/releases/download/v2.38.1.windows.1/MinGit-2.38.1-64-bit.zip"
    tar -xf mingit.zip -C .mingit
    del mingit.zip
) ELSE ( ECHO MinGit already installed. )
CALL :initgit
EXIT /B 0

:initgit
SET mingit=.mingit\mingw64\bin\git.exe
IF NOT EXIST ".git" (
    REM Make sure the CA certs are found. This sets mingit's default config to use its own certs (why is that not a thing?)
    %mingit% config --system http.sslcainfo .mingit\mingw64\ssl\certs\ca-bundle.crt
    REM Ensure this setting is set
    %mingit% config --system credential.helper manager-core
    ECHO Initializing git repo...
    %mingit% clone --no-checkout https://github.com/noccu/umamusu-translate.git gittmp
    REM cmdline mv wont deal with .files so we still require powershell
    powershell -command "mv gittmp\.git .git"
    DEL /Q gittmp
    REM Build index...
    %mingit% reset --quiet
) ELSE ( ECHO Already a Git repo. )
EXIT /B 0