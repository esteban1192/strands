@echo off
setlocal enabledelayedexpansion

REM Strands Liquibase Management Script for Windows
REM Usage: liquibase.bat [command] [options]

set SCRIPT_DIR=%~dp0
if "%LIQUIBASE_HOME%"=="" set LIQUIBASE_HOME=C:\liquibase
set LIQUIBASE=%LIQUIBASE_HOME%\liquibase.bat

REM Function to print colored output (basic version for Windows)
:print_info
echo [INFO] %~1
goto :eof

:print_success
echo [SUCCESS] %~1
goto :eof

:print_warning
echo [WARNING] %~1
goto :eof

:print_error
echo [ERROR] %~1
goto :eof

REM Check if Liquibase is installed
:check_liquibase
where liquibase >nul 2>nul
if %errorlevel% == 0 (
    set LIQUIBASE_CMD=liquibase
    goto :eof
)

if exist "%LIQUIBASE%" (
    set LIQUIBASE_CMD=%LIQUIBASE%
    goto :eof
)

call :print_error "Liquibase not found. Please install Liquibase or set LIQUIBASE_HOME."
call :print_info "Download from: https://github.com/liquibase/liquibase/releases"
exit /b 1

REM Function to run liquibase commands
:run_liquibase
set cmd=%~1
shift
set args=%*

call :print_info "Running: %LIQUIBASE_CMD% %cmd% %args%"

%LIQUIBASE_CMD% --defaults-file="%SCRIPT_DIR%liquibase.properties" %cmd% %args%
goto :eof

REM Show help
:show_help
echo Strands Database Management with Liquibase
echo.
echo Usage: %~nx0 [COMMAND] [OPTIONS]
echo.
echo Commands:
echo   update              Apply all pending changes to the database
echo   update-count N      Apply the next N changes to the database
echo   rollback TAG        Rollback to a specific tag
echo   rollback-count N    Rollback the last N changes
echo   status              Show pending changes
echo   validate            Validate the changelog
echo   generate-docs       Generate database documentation
echo   diff                Show differences between database and changelog
echo   tag TAG             Tag the current database state
echo   history             Show deployment history
echo   clear-checksums     Clear all checksums
echo.
echo Development Commands:
echo   dev-update          Apply changes with development context
echo   test-update         Apply changes with test context
echo   prod-update         Apply changes with production context
echo.
echo Examples:
echo   %~nx0 update                    # Apply all pending changes
echo   %~nx0 status                    # Check what changes are pending
echo   %~nx0 rollback-count 1          # Rollback the last change
echo   %~nx0 dev-update                # Update with development data
echo.
goto :eof

REM Main script logic
call :check_liquibase
if %errorlevel% neq 0 exit /b %errorlevel%

if "%1"=="update" (
    shift
    call :run_liquibase update %*
) else if "%1"=="update-count" (
    if "%2"=="" (
        call :print_error "Please specify the number of changes to apply"
        exit /b 1
    )
    call :run_liquibase update-count %2
) else if "%1"=="rollback" (
    if "%2"=="" (
        call :print_error "Please specify the tag to rollback to"
        exit /b 1
    )
    call :run_liquibase rollback %2
) else if "%1"=="rollback-count" (
    if "%2"=="" (
        call :print_error "Please specify the number of changes to rollback"
        exit /b 1
    )
    call :run_liquibase rollback-count %2
) else if "%1"=="status" (
    shift
    call :run_liquibase status %*
) else if "%1"=="validate" (
    shift
    call :run_liquibase validate %*
) else if "%1"=="generate-docs" (
    shift
    call :run_liquibase db-doc "./docs" %*
) else if "%1"=="diff" (
    shift
    call :run_liquibase diff %*
) else if "%1"=="tag" (
    if "%2"=="" (
        call :print_error "Please specify a tag name"
        exit /b 1
    )
    call :run_liquibase tag %2
) else if "%1"=="history" (
    shift
    call :run_liquibase history %*
) else if "%1"=="clear-checksums" (
    shift
    call :run_liquibase clear-checksums %*
) else if "%1"=="dev-update" (
    shift
    call :run_liquibase --contexts=development,all update %*
) else if "%1"=="test-update" (
    shift
    call :run_liquibase --contexts=test,all update %*
) else if "%1"=="prod-update" (
    shift
    call :run_liquibase --contexts=production,all update %*
) else if "%1"=="help" (
    call :show_help
) else if "%1"=="-h" (
    call :show_help
) else if "%1"=="--help" (
    call :show_help
) else if "%1"=="" (
    call :show_help
) else (
    call :print_error "Unknown command: %1"
    call :show_help
    exit /b 1
)