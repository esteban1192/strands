#!/bin/bash

# Strands Liquibase Management Script
# Usage: ./liquibase.sh [command] [options]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIQUIBASE_HOME="${LIQUIBASE_HOME:-/opt/liquibase}"
LIQUIBASE="$LIQUIBASE_HOME/liquibase"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Liquibase is installed
check_liquibase() {
    if ! command -v liquibase &> /dev/null && [ ! -f "$LIQUIBASE" ]; then
        print_error "Liquibase not found. Please install Liquibase or set LIQUIBASE_HOME."
        print_info "Download from: https://github.com/liquibase/liquibase/releases"
        exit 1
    fi
}

# Function to run liquibase commands
run_liquibase() {
    local cmd="$1"
    shift
    local args="$@"
    
    print_info "Running: liquibase $cmd $args"
    
    if command -v liquibase &> /dev/null; then
        liquibase --defaults-file="$SCRIPT_DIR/liquibase.properties" "$cmd" $args
    else
        "$LIQUIBASE" --defaults-file="$SCRIPT_DIR/liquibase.properties" "$cmd" $args
    fi
}

# Show help
show_help() {
    echo "Strands Database Management with Liquibase"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  update              Apply all pending changes to the database"
    echo "  update-count N      Apply the next N changes to the database"
    echo "  rollback TAG        Rollback to a specific tag"
    echo "  rollback-count N    Rollback the last N changes"
    echo "  status              Show pending changes"
    echo "  validate            Validate the changelog"
    echo "  generate-docs       Generate database documentation"
    echo "  diff                Show differences between database and changelog"
    echo "  tag TAG             Tag the current database state"
    echo "  history             Show deployment history"
    echo "  clear-checksums     Clear all checksums"
    echo ""
    echo "Development Commands:"
    echo "  dev-update          Apply changes with development context"
    echo "  test-update         Apply changes with test context"
    echo "  prod-update         Apply changes with production context"
    echo ""
    echo "Examples:"
    echo "  $0 update                    # Apply all pending changes"
    echo "  $0 status                    # Check what changes are pending"
    echo "  $0 rollback-count 1          # Rollback the last change"
    echo "  $0 dev-update                # Update with development data"
    echo ""
}

# Main script logic
main() {
    check_liquibase
    
    case "$1" in
        "update")
            shift
            run_liquibase update "$@"
            ;;
        "update-count")
            if [ -z "$2" ]; then
                print_error "Please specify the number of changes to apply"
                exit 1
            fi
            run_liquibase update-count "$2"
            ;;
        "rollback")
            if [ -z "$2" ]; then
                print_error "Please specify the tag to rollback to"
                exit 1
            fi
            run_liquibase rollback "$2"
            ;;
        "rollback-count")
            if [ -z "$2" ]; then
                print_error "Please specify the number of changes to rollback"
                exit 1
            fi
            run_liquibase rollback-count "$2"
            ;;
        "status")
            shift
            run_liquibase status "$@"
            ;;
        "validate")
            shift
            run_liquibase validate "$@"
            ;;
        "generate-docs")
            shift
            run_liquibase db-doc "./docs" "$@"
            ;;
        "diff")
            shift
            run_liquibase diff "$@"
            ;;
        "tag")
            if [ -z "$2" ]; then
                print_error "Please specify a tag name"
                exit 1
            fi
            run_liquibase tag "$2"
            ;;
        "history")
            shift
            run_liquibase history "$@"
            ;;
        "clear-checksums")
            shift
            run_liquibase clear-checksums "$@"
            ;;
        "dev-update")
            shift
            run_liquibase --contexts=development,all update "$@"
            ;;
        "test-update")
            shift
            run_liquibase --contexts=test,all update "$@"
            ;;
        "prod-update")
            shift
            run_liquibase --contexts=production,all update "$@"
            ;;
        "help"|"-h"|"--help"|"")
            show_help
            ;;
        *)
            print_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"