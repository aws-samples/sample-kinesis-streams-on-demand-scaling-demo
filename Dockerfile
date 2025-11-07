# Multi-stage build for optimized Python runtime
FROM --platform=linux/amd64 python:3.11-slim as builder

# Set build arguments for optimization
ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM --platform=linux/amd64 python:3.11-slim as production

# Set environment variables for Python optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Install runtime dependencies including AWS CLI for local development
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    && curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Create logs directory
RUN mkdir -p /app/logs && chown appuser:appuser /app/logs

# Switch to non-root user
USER appuser

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Health check using our custom health check script
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python health_check.py || exit 1

# Expose port for potential health check endpoint (optional)
EXPOSE 8080

# Set default environment variables (can be overridden)
ENV BASELINE_TPS=100 \
    SPIKE_TPS=10000 \
    PEAK_TPS=50000 \
    PER_TASK_CAPACITY=1000 \
    MAX_TASKS=100 \
    STREAM_NAME=social-media-stream \
    AWS_REGION=us-east-1 \
    PYTHONPATH=/app \
    # Container-specific metrics configuration
    CLOUDWATCH_NAMESPACE=KinesisOnDemandDemo \
    SERVICE_NAME=kinesis-data-generator \
    CLUSTER_NAME=kinesis-demo-cluster \
    ENVIRONMENT=development \
    DEPLOYMENT_ID=default \
    METRICS_PUBLISH_INTERVAL=10 \
    ENABLE_CLOUDWATCH_METRICS=true \
    # Controller mode configuration
    CONTROLLER_MODE=internal \
    PARAMETER_PREFIX=/kinesis-demo

# Use entrypoint script for better container management
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (can be overridden)
CMD []