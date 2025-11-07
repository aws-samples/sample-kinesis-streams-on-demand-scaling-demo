#!/bin/bash
set -e

# Container entrypoint script for Kinesis On-Demand Demo Data Generator
# Provides configuration validation, health checks, and graceful startup

echo "=== Kinesis On-Demand Demo Data Generator ==="
echo "Container starting at $(date)"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Validate required environment variables
validate_environment() {
    log "Validating environment variables..."
    
    local required_vars=("AWS_REGION" "STREAM_NAME")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log "ERROR: Missing required environment variables: ${missing_vars[*]}"
        exit 1
    fi
    
    log "Environment validation passed"
    
    # Log configuration (without sensitive data)
    log "Configuration:"
    log "  AWS_REGION: ${AWS_REGION}"
    log "  STREAM_NAME: ${STREAM_NAME}"

    log ""
    log "Container Metrics Configuration:"
    log "  CLOUDWATCH_NAMESPACE: ${CLOUDWATCH_NAMESPACE:-KinesisOnDemandDemo}"
    log "  SERVICE_NAME: ${SERVICE_NAME:-kinesis-data-generator}"
    log "  CLUSTER_NAME: ${CLUSTER_NAME:-kinesis-demo-cluster}"
    log "  ENVIRONMENT: ${ENVIRONMENT:-development}"
    log "  DEPLOYMENT_ID: ${DEPLOYMENT_ID:-default}"
    log "  CONTAINER_ID: ${CONTAINER_ID:-auto-detected}"
    log "  METRICS_PUBLISH_INTERVAL: ${METRICS_PUBLISH_INTERVAL:-10}"
    log "  ENABLE_CLOUDWATCH_METRICS: ${ENABLE_CLOUDWATCH_METRICS:-true}"
}

# Check AWS credentials
check_aws_credentials() {
    log "Checking AWS credentials..."
    
    # Check for different credential sources
    if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
        log "Found AWS credentials in environment variables"
    elif [[ -f "/home/appuser/.aws/credentials" ]]; then
        log "Found AWS credentials file at /home/appuser/.aws/credentials"
    elif [[ -f "/home/appuser/.aws/config" ]]; then
        log "Found AWS config file at /home/appuser/.aws/config"
    else
        log "No explicit AWS credentials found - will rely on IAM roles or instance metadata"
    fi
    
    if command_exists aws; then
        log "Testing AWS credentials with STS call..."
        if aws sts get-caller-identity >/dev/null 2>&1; then
            local identity=$(aws sts get-caller-identity --output text --query 'Arn' 2>/dev/null || echo "unknown")
            log "✅ AWS credentials valid for: $identity"
        else
            log "❌ AWS credentials test failed. Error details:"
            aws sts get-caller-identity 2>&1 | head -5 | while read line; do
                log "   $line"
            done
            log "This may cause issues with Kinesis and CloudWatch operations"
            log "Please check your AWS credentials configuration"
        fi
    else
        log "AWS CLI not available, skipping credential validation"
    fi
}

# Perform health check
perform_health_check() {
    log "Performing initial health check..."
    
    if python health_check.py >/dev/null 2>&1; then
        log "Health check passed"
    else
        log "WARNING: Health check failed, but continuing startup"
        # Show health check output for debugging
        python health_check.py || true
    fi
}

# Create necessary directories
setup_directories() {
    log "Setting up directories..."
    
    # Create logs directory if it doesn't exist
    mkdir -p /app/logs
    
    # Ensure proper permissions
    if [[ $(id -u) -eq 0 ]]; then
        chown -R appuser:appuser /app/logs
    fi
    
    log "Directory setup complete"
}

# Handle shutdown signals gracefully
setup_signal_handlers() {
    log "Setting up signal handlers..."
    
    # Function to handle shutdown
    shutdown() {
        log "Received shutdown signal, stopping gracefully..."
        if [[ -n "$MAIN_PID" ]]; then
            kill -TERM "$MAIN_PID" 2>/dev/null || true
            wait "$MAIN_PID" 2>/dev/null || true
        fi
        log "Shutdown complete"
        exit 0
    }
    
    # Set up signal traps
    trap shutdown SIGTERM SIGINT
}

# Main startup function
main() {
    log "Starting container initialization..."
    
    # Run initialization steps
    validate_environment
    setup_directories
    check_aws_credentials
    perform_health_check
    setup_signal_handlers
    
    log "Initialization complete, starting main application..."
    
    # Start the main application
    if [[ "$1" == "health-check" ]]; then
        # Run health check only
        exec python health_check.py
    elif [[ "$1" == "shell" ]]; then
        # Start interactive shell for debugging
        exec /bin/bash
    else
        # Start main application
        exec python main.py &
        MAIN_PID=$!
        
        # Wait for the main process
        wait $MAIN_PID
    fi
}

# Handle different startup modes
case "${1:-}" in
    "health-check")
        log "Running health check only..."
        exec python health_check.py
        ;;
    "shell")
        log "Starting interactive shell..."
        exec /bin/bash
        ;;
    "")
        # Default: start main application
        main "$@"
        ;;
    *)
        # Pass through any other commands
        log "Executing custom command: $*"
        exec "$@"
        ;;
esac