# Kinesis On-Demand Demo

A comprehensive demonstration platform showcasing Amazon Kinesis Data Streams' automatic scaling capabilities through a realistic social media viral event simulation.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Demo Phases](#demo-phases)
- [Local Development](#local-development)
- [Container Application](#container-application)
- [Infrastructure (CDK)](#infrastructure-cdk)
- [Metrics and Monitoring](#metrics-and-monitoring)
- [TPS Control Logic](#tps-control-logic)
- [Security](#security)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## ⚠️ Important Disclaimer - Non-Production Use Only

**THIS DEMO IS FOR TESTING AND EDUCATIONAL PURPOSES ONLY**

This Demo is designed exclusively for:
- **Development and testing environments**
- **Educational and learning purposes**
- **Proof-of-concept demonstrations**
- **Performance benchmarking and testing**

**DO NOT USE IN PRODUCTION:**
- ❌ Do not deploy in production AWS accounts
- ❌ Do not use with real customer data
- ❌ Do not use for mission-critical applications
- ❌ Do not leave running unattended for extended periods

**COST AND BILLING WARNINGS:**
- 💰 This demo generates high-volume synthetic traffic (up to 50,000+ messages/second)
- 💰 Warm throughput features enable minimum billing commitments
- 💰 Demo execution will incur AWS charges for Kinesis, ECS, Lambda, and other services
- 💰 Always monitor AWS costs and set up billing alerts
- 💰 Use dedicated testing AWS accounts with appropriate cost controls

**RECOMMENDED SAFETY MEASURES:**
- ✅ Use separate AWS accounts for testing
- ✅ Set up AWS billing alerts and budgets
- ✅ Review AWS pricing before enabling warm throughput
- ✅ Clean up resources after demo completion using the cleanup command
- ✅ Monitor resource usage during demo execution

By using this demo, you acknowledge that you understand these limitations and will use it responsibly in appropriate non-production environments.

## Overview

> **⚠️ IMPORTANT: This is a demonstration and testing tool designed for non-production environments only. Do not use this demo in production AWS accounts or with production workloads. The demo generates high-volume synthetic traffic and may incur AWS charges.**

The Kinesis On-Demand Demo is designed to showcase Amazon Kinesis Data Streams' automatic scaling capabilities through a realistic social media viral event simulation. The application orchestrates social media post generation and Kinesis publishing with phase-based traffic control and comprehensive monitoring.

**This demo is intended for:**
- Learning and educational purposes
- Development and testing environments
- Proof-of-concept demonstrations
- Performance testing and benchmarking

**This demo is NOT intended for:**
- Production workloads or environments
- Processing real customer data
- Mission-critical applications
- Long-term operational use

### Key Features

- Generate realistic social media posts with configurable traffic patterns
- Publish posts to Amazon Kinesis Data Streams in On-Demand mode
- **NEW**: Support for Kinesis warm throughput for instant scaling capacity
- Demonstrate automatic scaling from 100 to 50,000+ messages per second
- Provide real-time metrics and monitoring through CloudWatch
- Support deployment on Amazon ECS Fargate for scalable traffic generation
- Comprehensive demo management script with warm throughput configuration

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Container     │    │   Amazon         │    │   CloudWatch    │
│   Application   │───▶│   Kinesis        │───▶│   Metrics       │
│   (ECS Fargate) │    │   Data Streams   │    │   Dashboard     │
└─────────────────┘    │   (On-Demand)    │    └─────────────────┘
                       └──────────────────┘
```

### Infrastructure Components

1. **Amazon Kinesis Data Streams** - On-Demand mode stream for automatic scaling
2. **Amazon ECS Fargate** - Containerized data generators with auto-scaling
3. **AWS Step Functions** - Demo orchestration and phase management
4. **AWS Lambda Functions** - Message processing and cost calculation
5. **Amazon CloudWatch** - Comprehensive monitoring and dashboards
6. **Amazon VPC** - Secure networking infrastructure

## Project Structure

```
kinesis-ondemand-demo/
├── README.md                    # This comprehensive guide
├── requirements.txt             # Python dependencies
├── pytest.ini                  # Pytest configuration
├── run_tests.py                # Simple test runner script
├── main.py                     # Main application entry point
├── health_check.py             # Health check utilities
├── demo_post_generation.py     # Post generation demo
├── Dockerfile                  # Container image definition
├── docker-compose.yml          # Local development setup
├── build.sh                    # Container build script
├── entrypoint.sh               # Container entrypoint
├── check-credentials.sh        # AWS credentials checker
├── .env.example                # Environment variables template
│
├── infrastructure/              # CDK infrastructure code
│   ├── src/                    # TypeScript CDK source
│   ├── test/                   # Infrastructure tests
│   ├── scripts/                # Deployment scripts
│   └── README.md               # Infrastructure documentation
│
├── lambda/                     # Lambda function implementations
│   └── .gitkeep                # Placeholder for Lambda functions
│
├── ecs/                        # ECS container applications
│   └── .gitkeep                # Placeholder for containerized apps
│
├── shared/                     # Shared Python modules and utilities
│   ├── __init__.py             # Package initialization
│   ├── models.py               # Core data models
│   ├── serialization.py        # JSON serialization utilities
│   ├── config.py               # Configuration management
│   ├── post_generator.py       # Social media post generation
│   ├── kinesis_producer.py     # Kinesis producer with error handling
│   ├── cloudwatch_metrics.py   # CloudWatch metrics publishing
│   ├── env_phase_controller.py # Environment-based phase control

│   └── stepfunctions_phase_controller.py # Step Functions integration
│
├── step-functions/             # Step Functions state machine
│   ├── step_functions_controller.py # Controller implementation
│   ├── demo_state_machine.json # State machine definition
│   └── STEP_FUNCTIONS_ARCHITECTURE.md # Architecture docs
│

├── examples/                   # Example scripts and demos
│   ├── kinesis_producer_example.py # Producer examples
│   ├── metrics_demo.py         # Metrics demonstration
│   ├── metrics_demo_offline.py # Offline metrics demo
│   ├── windowed_metrics_demo.py # Windowed metrics
│   ├── container-metrics-examples.md # Container metrics guide
│   └── deploy-to-ecs.sh        # ECS deployment script
│
└── tests/                      # Test suites
    ├── __init__.py             # Test package initialization
    ├── test_models.py          # Unit tests for data models
    ├── test_serialization.py   # Unit tests for serialization
    ├── test_config.py          # Unit tests for configuration

    ├── test_kinesis_producer.py # Producer tests
    ├── test_cloudwatch_metrics.py # Metrics tests
    ├── test_integration_data_generator.py # Integration tests
    ├── test_producer_metrics_integration.py # Metrics integration
    └── test_requirements_validation.py # Requirements validation
```

## Quick Start

> **🚨 NON-PRODUCTION USE ONLY**: This demo is designed for testing and demonstration purposes. Use only in development/testing AWS accounts. The demo generates synthetic high-volume traffic and will incur AWS charges.

### Prerequisites

- Python 3.8+ installed
- Docker and Docker Compose installed
- **Non-production AWS account** with appropriate permissions
- AWS credentials configured
- Latest version of AWS CLI >= 2.31.x
- Understanding that this demo will generate AWS charges

### 1. Configure AWS Credentials

```bash
# Quick credential check (recommended)
export AWS_REGION=<AWS REGION CODE>
./check-credentials.sh

# Or manually verify credentials are available
aws sts get-caller-identity
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# Update STREAM_NAME to your Kinesis stream name
```

### 3. Deploy AWS CDK Stack (Required)

For full production deployment:

```bash
cd infrastructure
npm install
./scripts/deploy.sh --environment production
```

### 4. Run the Demo

**🎯 Method 1: Demo Manager Script (Recommended)**
```bash
# Standard demo without warm throughput
./infrastructure/scripts/demo-manager.sh start

# Demo with 100 MB/s warm throughput
./infrastructure/scripts/demo-manager.sh start --warm-throughput 100

# Setup infrastructure only with warm throughput
./infrastructure/scripts/demo-manager.sh setup --warm-throughput 50
```

**🎯 Method 2: Docker Compose**
```bash
# Build and start the container with your configuration
docker-compose up --build

# Or run in background
docker-compose up -d --build

# View logs
docker-compose logs -f
```

**⚡ Method 3: Build Script (Quick Testing)**
```bash
# Quick test run with reduced TPS values (no configuration needed)
./build.sh run
```



## Demo Manager Script

> **⚠️ NON-PRODUCTION WARNING**: This script creates real AWS resources and generates high-volume traffic. Use only in development/testing environments. Monitor AWS costs during demo execution.

The `demo-manager.sh` script provides comprehensive management of the Kinesis On-Demand demo with support for the new warm throughput feature.

### Prerequisites for Warm Throughput

Before using warm throughput features, you must enable Kinesis On-Demand Advantage billing:

```bash
# Check current billing status
./infrastructure/scripts/demo-manager.sh check-advantage

# Enable On-Demand Advantage billing (one-time setup)
./infrastructure/scripts/demo-manager.sh enable-advantage
```

**Important Notes:**
- **NON-PRODUCTION USE ONLY**: This demo is for testing and demonstration purposes
- Warm throughput requires Kinesis On-Demand Advantage billing mode
- This enables minimum throughput billing commitment for your AWS account
- **BILLING IMPACT**: Warm throughput and high-volume traffic will generate AWS charges
- Review pricing at: https://aws.amazon.com/kinesis/data-streams/pricing/
- Valid throughput range: 1-10240 MB/s (10 GB/s maximum)
- **Use dedicated testing AWS accounts only**

### Basic Usage

**Standard Demo (No Warm Throughput):**
```bash
# Start complete demo (infrastructure + execution)
./infrastructure/scripts/demo-manager.sh start

# Setup infrastructure only
./infrastructure/scripts/demo-manager.sh setup

# Check infrastructure health
./infrastructure/scripts/demo-manager.sh health

# Clean up resources
./infrastructure/scripts/demo-manager.sh cleanup
```

**With Warm Throughput:**
```bash
# Start demo with 100 MB/s warm throughput
./infrastructure/scripts/demo-manager.sh start --warm-throughput 100

# Setup infrastructure with 50 MB/s warm throughput
./infrastructure/scripts/demo-manager.sh setup --warm-throughput 50

# Update existing stream with warm throughput
./infrastructure/scripts/demo-manager.sh start --warm-throughput 200
```

### Demo Management Commands

| Command | Description | Example |
|---------|-------------|---------|
| `start` | Start complete demo (setup + execution) | `./demo-manager.sh start --warm-throughput 100` |
| `setup` | Setup infrastructure only | `./demo-manager.sh setup --warm-throughput 50` |
| `list` | List recent demo executions | `./demo-manager.sh list` |
| `status <arn>` | Get detailed execution status | `./demo-manager.sh status arn:aws:states:...` |
| `stop <arn>` | Stop running execution | `./demo-manager.sh stop arn:aws:states:...` |
| `logs <arn>` | Show execution logs | `./demo-manager.sh logs arn:aws:states:...` |
| `cleanup` | Clean up all resources | `./demo-manager.sh cleanup` |
| `health` | Check infrastructure health | `./demo-manager.sh health` |
| `test` | Test AWS connectivity | `./demo-manager.sh test` |

### Warm Throughput Management

| Command | Description | Example |
|---------|-------------|---------|
| `enable-advantage` | Enable On-Demand Advantage billing | `./demo-manager.sh enable-advantage` |
| `check-advantage` | Check billing mode status | `./demo-manager.sh check-advantage` |

### Command Options

| Option | Description | Example |
|--------|-------------|---------|
| `-r, --region` | AWS region | `--region us-west-2` |
| `-e, --environment` | Environment name | `--environment staging` |
| `-w, --warm-throughput` | Warm throughput in MB/s | `--warm-throughput 100` |
| `-h, --help` | Show help | `--help` |

### Warm Throughput Examples

**Enable Billing and Start Demo:**
```bash
# One-time setup: Enable On-Demand Advantage billing
./infrastructure/scripts/demo-manager.sh enable-advantage

# Start demo with 100 MB/s warm throughput
./infrastructure/scripts/demo-manager.sh start --warm-throughput 100
```

**Different Throughput Levels:**
```bash
# Low throughput for testing (10 MB/s)
./infrastructure/scripts/demo-manager.sh setup --warm-throughput 10

# Medium throughput for moderate load (500 MB/s)
./infrastructure/scripts/demo-manager.sh start --warm-throughput 500

# High throughput for peak events (2000 MB/s)
./infrastructure/scripts/demo-manager.sh start --warm-throughput 2000
```

**Multi-Environment Usage:**
```bash
# Production environment with high throughput
./infrastructure/scripts/demo-manager.sh start \
  --environment production \
  --region us-east-1 \
  --warm-throughput 1000

# Staging environment with lower throughput
./infrastructure/scripts/demo-manager.sh setup \
  --environment staging \
  --region us-west-2 \
  --warm-throughput 100
```

### Monitoring Warm Throughput

The script provides enhanced status reporting for warm throughput:

```bash
# Check current status (includes warm throughput info)
./infrastructure/scripts/demo-manager.sh status arn:aws:states:...

# Health check (shows billing mode and throughput config)
./infrastructure/scripts/demo-manager.sh health
```

**Sample Output:**
```
📊 Kinesis Stream Status:
  Status: ACTIVE
  Warm Throughput: Current 100 MB/s, Target 100 MB/s

💳 Billing Configuration:
  On-Demand Advantage: Enabled (warm throughput available)
```

### Troubleshooting Warm Throughput

**Common Issues:**

1. **Billing Mode Not Enabled:**
   ```bash
   Error: Kinesis On-Demand Advantage billing must be enabled
   Solution: ./demo-manager.sh enable-advantage
   ```

2. **Invalid Throughput Value:**
   ```bash
   Error: Invalid warm throughput value. Must be between 1 and 10240 MB/s
   Solution: Use value between 1-10240
   ```

3. **Insufficient Permissions:**
   ```bash
   Error: Missing Kinesis UpdateStreamWarmThroughput permission
   Solution: Add kinesis:UpdateStreamWarmThroughput to IAM policy
   ```

## Demo Phases

The application progresses through four distinct phases:

1. **Baseline Phase (0-2 min)**: 100 messages/second - Normal social media traffic
2. **Spike Phase (2-4 min)**: 10,000+ messages/second - Breaking news event
3. **Peak Phase (4-6 min)**: 50,000+ messages/second - Viral moment
4. **Decline Phase (6-8 min)**: Back to baseline - Event subsides

### Sample Generated Posts

#### Phase 1 (Baseline - 100 TPS):
```
"Quick take on today's big news #News #TechNews"
User: techexpert247
Location: New York, USA
Engagement: 1.2
```

#### Phase 2 (Spike - 10,000 TPS):
```
"🚨 URGENT: This changes everything in the industry #BreakingNews #GameChanger #Innovation"
User: cloudninja89
Location: Tokyo, Japan
Engagement: 6.4
```

#### Phase 3 (Peak Viral - 50,000 TPS):
```
"This is absolutely incredible! Everyone needs to see this #Viral #Amazing #Unbelievable #MustSee #Incredible #Shocking 🔥"
User: socialguru456
Location: Sydney, Australia
Mentions: @techfan99 @newslover88 @digitalace
Engagement: 18.3
```

## Local Development

### Configuration Options

#### Demo Traffic Configuration

Adjust traffic patterns in `.env`:
```bash
BASELINE_TPS=100      # Phase 1 & 4: Baseline traffic
SPIKE_TPS=10000       # Phase 2: Spike traffic  
PEAK_TPS=50000        # Phase 3: Peak traffic
```

#### Controller Modes

For local development, use internal mode:
```bash
CONTROLLER_MODE=internal  # Each container manages its own phases
```

For testing Step Functions integration:
```bash
CONTROLLER_MODE=step_functions  # Requires Step Functions deployment
```

#### Metrics Configuration

Configure CloudWatch metrics publishing:
```bash
ENABLE_CLOUDWATCH_METRICS=true   # Enable/disable metrics
METRICS_PUBLISH_INTERVAL=10      # Publish interval in seconds
CLOUDWATCH_NAMESPACE=KinesisOnDemandDemo  # CloudWatch namespace
```

### Development Commands

```bash
# Build the container
docker-compose build

# Run the demo
docker-compose up

# Run in background
docker-compose up -d

# Stop the demo
docker-compose down

# View logs
docker-compose logs -f

# Access container shell
docker-compose exec kinesis-data-generator bash

# Run health check
docker-compose exec kinesis-data-generator python health_check.py
```

### Local Testing with LocalStack

For testing without AWS costs, use LocalStack:

```bash
# Start with LocalStack
docker-compose --profile local-testing up

# Configure for LocalStack
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
```

## Container Application

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for Kinesis stream |
| `STREAM_NAME` | `social-media-stream` | Kinesis stream name |
| `BASELINE_TPS` | `100` | Messages per second in baseline phase |
| `SPIKE_TPS` | `10000` | Messages per second in spike phase |
| `PEAK_TPS` | `50000` | Messages per second in peak phase |
| `PER_TASK_CAPACITY` | `1000` | Messages per second per container |
| `MAX_TASKS` | `100` | Maximum number of containers |

### Container Metrics Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUDWATCH_NAMESPACE` | `KinesisOnDemandDemo` | CloudWatch metrics namespace |
| `SERVICE_NAME` | `kinesis-data-generator` | Service name for metrics dimensions |
| `CLUSTER_NAME` | `kinesis-demo-cluster` | Cluster name for metrics dimensions |
| `ENVIRONMENT` | `development` | Environment name (dev/staging/prod) |
| `DEPLOYMENT_ID` | `default` | Unique deployment identifier |
| `CONTAINER_ID` | `auto-detected` | Container identifier (auto-detected if not set) |
| `METRICS_PUBLISH_INTERVAL` | `10` | CloudWatch metrics publish interval (seconds) |
| `ENABLE_CLOUDWATCH_METRICS` | `true` | Enable/disable CloudWatch metrics publishing |

### Build Script Usage

```bash
# Build the image
./build.sh build

# Run tests
./build.sh test

# Push to registry
./build.sh push -r your-registry.com

# Run locally
./build.sh run

# Clean up
./build.sh clean

# Complete pipeline
./build.sh all -t v1.0.0 -r your-registry.com
```

### Health Checks

The container includes comprehensive health checks:

```bash
# Run health check
docker exec container-name python health_check.py

# Health check output
{
  "timestamp": "2024-01-15T10:30:00Z",
  "overall_status": "healthy",
  "checks": {
    "python_environment": {"status": "healthy"},
    "aws_credentials": {"status": "healthy"},
    "environment_variables": {"status": "healthy"},
    "shared_modules": {"status": "healthy"}
  }
}
```

## Infrastructure (CDK)

> **🚨 PRODUCTION WARNING**: This infrastructure creates real AWS resources that will incur charges. Deploy only in development/testing AWS accounts. The demo generates high-volume traffic and is not suitable for production use.

### Prerequisites

#### Software Requirements

- **Node.js** (v16 or later)
- **npm** (v8 or later)
- **AWS CLI** (v2.x)
- **AWS CDK** (v2.87.0 or later)
- **TypeScript** (v4.9.5 or later)

### Deployment

#### Using the Demo Manager Script (Recommended)

The demo manager script provides the easiest way to deploy and manage the demo:

```bash
# Complete demo setup with warm throughput
./infrastructure/scripts/demo-manager.sh start --warm-throughput 100

# Infrastructure-only deployment
./infrastructure/scripts/demo-manager.sh setup --warm-throughput 50

# Check deployment status
./infrastructure/scripts/demo-manager.sh health
```

#### Using the CDK Deployment Script

For advanced infrastructure management:

```bash
cd infrastructure

# Install dependencies
npm install

# Deploy to production (default)
./scripts/deploy.sh

# Deploy to staging with diff preview
./scripts/deploy.sh --environment staging --diff

# Bootstrap CDK and deploy
./scripts/deploy.sh --bootstrap --environment production

# Destroy infrastructure
./scripts/deploy.sh --destroy --environment staging
```

#### Using CDK Directly

```bash
cd infrastructure

# Bootstrap CDK (first time only)
npx cdk bootstrap

# Deploy stack
npx cdk deploy --context environment=production

# Show differences
npx cdk diff --context environment=production

# Destroy stack
npx cdk destroy --context environment=production
```

### Infrastructure Components

#### Networking (VPC)
- **VPC** with public and private subnets across 2 AZs
- **NAT Gateway** for private subnet internet access
- **Internet Gateway** for public subnet access
- **Route Tables** with appropriate routing

#### Kinesis Data Streams
- **Stream Mode**: On-Demand for automatic scaling
- **Retention**: 24 hours
- **Encryption**: Server-side with AWS managed keys
- **Monitoring**: Enhanced metrics enabled

#### ECS Infrastructure
- **Cluster**: Fargate-based with container insights
- **Task Definition**: 1 vCPU, 2GB memory, optimized for data generation
- **Service**: Auto-scaling from 1 to 50 tasks
- **Auto Scaling**: CPU-based scaling policies
- **Health Checks**: Container-level health monitoring

#### Lambda Functions

**Message Processor**
- **Runtime**: Python 3.12
- **Memory**: 256 MB
- **Timeout**: 5 minutes
- **Trigger**: Kinesis stream events
- **Purpose**: Process social media posts and calculate metrics

**Cost Calculator**
- **Runtime**: Python 3.12
- **Memory**: 256 MB
- **Timeout**: 2 minutes
- **Purpose**: Real-time cost calculation and optimization tracking

**Step Functions Controller**
- **Runtime**: Python 3.12
- **Memory**: 256 MB
- **Timeout**: 2 minutes
- **Purpose**: ECS service orchestration and phase management

#### Step Functions State Machine
- **Type**: Standard workflow
- **Phases**: 4-phase demo progression (baseline → spike → peak → decline)
- **Timing**: 2 minutes per phase (8 minutes total)
- **Error Handling**: Built-in retry logic and failure recovery
- **State Management**: Automatic state persistence

## Metrics and Monitoring

### CloudWatch Metrics Publisher

The core metrics publishing component that handles:

- Periodic publishing of producer metrics to CloudWatch
- Batch processing with CloudWatch API limits (20 metrics per batch)
- Exponential backoff retry logic for throttling scenarios
- Consistent dimensions for CloudWatch native aggregation
- Custom metric publishing capabilities

### Metrics Published

All metrics are published with consistent dimensions for CloudWatch native aggregation:

| Metric Name | Unit | Description | Dimensions |
|-------------|------|-------------|------------|
| `MessagesPerSecond` | Count/Second | Rate of messages sent to Kinesis | ServiceName, ContainerID, ClusterName, DemoPhase |
| `BatchesPerSecond` | Count/Second | Rate of batch operations | ServiceName, ContainerID, ClusterName, DemoPhase |
| `ThrottleExceptionsPerSecond` | Count/Second | Rate of throttling exceptions | ServiceName, ContainerID, ClusterName, DemoPhase |
| `RetriesPerSecond` | Count/Second | Rate of retry operations | ServiceName, ContainerID, ClusterName, DemoPhase |
| `AverageLatency` | Milliseconds | Average end-to-end latency | ServiceName, ContainerID, ClusterName, DemoPhase |
| `SuccessRate` | Percent | Percentage of successful operations | ServiceName, ContainerID, ClusterName, DemoPhase |

### CloudWatch Dashboard

The stack creates a comprehensive dashboard with:

1. **Traffic Volume Graph**: Real-time message throughput
2. **Scaling Timeline**: ECS task count changes
3. **Throttle Monitor**: Kinesis throttle exceptions
4. **Latency Tracking**: End-to-end processing latency
5. **Cost Meter**: Running demo costs
6. **Phase Indicator**: Current demo phase

### Usage Example

```python
from shared.cloudwatch_metrics import CloudWatchMetricsPublisher
from shared.config import DemoConfig

config = DemoConfig()
async with CloudWatchMetricsPublisher(
    config, 
    service_name="kinesis-data-generator",
    cluster_name="kinesis-demo-cluster"
) as publisher:
    await publisher.publish_producer_metrics(producer_metrics, demo_phase=2)
```

## TPS Control Logic

### Complete Logic Flow

#### 1. Main Demo Loop (`main.py`)

The main loop runs continuously with a 0.1-second sleep:

```python
async def _run_demo_loop(self) -> None:
    while self.is_running and not self.shutdown_requested:
        # Generate and send posts for current second
        await self._generate_and_send_posts()
        
        # Sleep for remainder of second to maintain timing
        await asyncio.sleep(0.1)  # Small sleep to prevent busy waiting
```

#### 2. Calculate Messages Per Second

Every loop iteration calls the traffic controller to determine how many messages to generate:

```python
async def _generate_and_send_posts(self) -> None:
    # Calculate how many messages to generate (1-second window)
    messages_to_generate = self.traffic_controller.calculate_messages_to_generate(1.0)
    
    if messages_to_generate == 0:
        return
```

#### 3. Environment Controller Calculation

The environment controller reads from environment variables and enforces limits:

```python
def calculate_messages_to_generate(self, time_window_seconds: float = 1.0) -> int:
    # Get current values from environment variables
    target_tps = self.get_target_tps()                              # Reads TARGET_TPS env var
    per_task_capacity = int(os.getenv('PER_TASK_CAPACITY', '1000')) # Reads capacity limit
    
    # Enforce per-task capacity limit (safety mechanism)
    effective_tps = min(target_tps, per_task_capacity)
    
    # Calculate messages for time window (usually 1.0 second)
    return int(effective_tps * time_window_seconds)
```

### Example Scenarios

#### Phase 1: Baseline (100 TPS)
```
Environment Variables:
- DEMO_PHASE=1
- TARGET_TPS=100
- PER_TASK_CAPACITY=1000

Calculation:
effective_tps = min(100, 1000) = 100
messages_to_generate = 100 * 1.0 = 100

Result: Generates 100 posts per second
```

#### Phase 2: Spike (1000 TPS per task)
```
Environment Variables:
- DEMO_PHASE=2  
- TARGET_TPS=1000 (calculated by Step Functions: 10000 total ÷ 10 tasks)
- PER_TASK_CAPACITY=1000

Calculation:
effective_tps = min(1000, 1000) = 1000
messages_to_generate = 1000 * 1.0 = 1000

Result: Generates 1000 posts per second per task
```

### Key Features

1. **Dynamic Reading**: Environment variables read fresh each time
2. **Safety Limits**: PER_TASK_CAPACITY prevents runaway generation  
3. **Precise Control**: Exact number of posts generated per target TPS
4. **Phase Awareness**: Post types change based on current phase
5. **Batch Efficiency**: Large volumes handled in manageable batches

## Security

### Current Security Posture

**✅ Strengths:**
- No unauthenticated API endpoints (API Gateway removed)
- Latest Lambda runtimes (Python 3.12) with security patches
- Comprehensive Step Functions logging and tracing
- Scoped ECR and CloudWatch permissions with documented justifications
- Proper IAM service principals and least privilege where possible
- All security findings addressed or properly suppressed

### Security Features

#### Container Security
- Runs as non-root user (`appuser`)
- Minimal base image (Python slim)
- No unnecessary packages or tools
- Read-only filesystem where possible

#### AWS Permissions

Required IAM permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kinesis:PutRecord",
        "kinesis:PutRecords",
        "kinesis:DescribeStream"
      ],
      "Resource": "arn:aws:kinesis:*:*:stream/social-media-stream"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

**Additional permissions for warm throughput features:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kinesis:UpdateStreamWarmThroughput",
        "kinesis:DescribeAccountSettings",
        "kinesis:UpdateAccountSettings"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Network Security
- **VPC**: Isolated network environment
- **Security Groups**: Minimal required access
- **Subnets**: Public/private separation
- **NAT Gateway**: Secure outbound internet access

#### Encryption
- **Kinesis Stream**: Server-side encryption with AWS managed keys
- **CloudWatch Logs**: Default encryption
- **ECS**: Encryption in transit and at rest

### Security Scan Results

**📊 All Security Issues Resolved:**
- ✅ AwsSolutions-L1 (Lambda Runtime): RESOLVED (Python 3.12)
- ✅ AwsSolutions-SF1 (Step Functions Logging): RESOLVED  
- ✅ AwsSolutions-SF2 (Step Functions Tracing): RESOLVED
- ✅ AwsSolutions-IAM5 (IAM Wildcards): SUPPRESSED WITH JUSTIFICATION
- ✅ AwsSolutions-ECS2 (Environment Variables): SUPPRESSED WITH JUSTIFICATION
- ✅ API Gateway Issues: ELIMINATED (Gateway Removed)

**Final Status: SECURITY SCAN PASSED** ✅

## Testing

### Unit Tests

Run the comprehensive test suite:

```bash
# Run all tests
./build.sh test

# Or with pytest directly
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_cloudwatch_metrics.py -v
python -m pytest tests/test_kinesis_producer.py -v


# Run with coverage
python -m pytest tests/ --cov=shared --cov-report=html
```

### Integration Tests

```bash
# Test with LocalStack
docker-compose --profile local-testing up -d localstack
docker-compose run kinesis-data-generator python -m pytest tests/test_integration_data_generator.py

# Test with real AWS services (requires credentials)
export AWS_REGION=us-east-1
export STREAM_NAME=test-stream
./build.sh test
```

### Load Testing

```bash
# Run multiple containers for load testing
docker-compose up --scale kinesis-data-generator=3

# Monitor resource usage
docker stats
```

### Infrastructure Tests

```bash
cd infrastructure

# Run all tests
npm test

# Run tests with coverage
npm run test -- --coverage

# Run specific test file
npm test -- kinesis-ondemand-demo-stack.test.ts
```

## Troubleshooting

### Common Issues

#### AWS Credentials Issues

If you see AWS credential errors:

1. **Check credential configuration**:
   ```bash
   docker-compose exec kinesis-data-generator aws sts get-caller-identity
   ```

2. **Verify environment variables**:
   ```bash
   docker-compose exec kinesis-data-generator env | grep AWS
   ```

3. **Check mounted credentials**:
   ```bash
   docker-compose exec kinesis-data-generator ls -la /home/appuser/.aws/
   ```

#### Common Error Messages

**"Unable to locate credentials"**
- Ensure AWS credentials are set in `.env` file or AWS credentials file is mounted
- Check that environment variables are properly loaded

**"Stream does not exist"**
- Create the Kinesis stream in your AWS account
- Verify the stream name matches the `STREAM_NAME` environment variable

**"Access denied"**
- Ensure your AWS credentials have permissions for:
  - `kinesis:PutRecord`
  - `kinesis:PutRecords`
  - `kinesis:DescribeStream`
  - `cloudwatch:PutMetricData`
  - `logs:CreateLogGroup`
  - `logs:CreateLogStream`
  - `logs:PutLogEvents`
- For warm throughput features, also ensure:
  - `kinesis:UpdateStreamWarmThroughput`
  - `kinesis:DescribeAccountSettings`
  - `kinesis:UpdateAccountSettings`

#### Performance Issues

If the container is slow or consuming too many resources:

1. **Adjust resource limits** in docker-compose.yml:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '1.0'
         memory: 512M
   ```

2. **Reduce traffic rates** in `.env`:
   ```bash
   BASELINE_TPS=10
   SPIKE_TPS=1000
   PEAK_TPS=5000
   ```

3. **Disable metrics** for testing:
   ```bash
   ENABLE_CLOUDWATCH_METRICS=false
   ```

### Debug Mode

```bash
# Run with debug logging
docker run -e LOG_LEVEL=DEBUG kinesis-ondemand-demo

# Interactive debugging
docker run -it kinesis-ondemand-demo shell
```

### Infrastructure Troubleshooting

#### CDK Bootstrap Required
```bash
Error: Need to perform AWS CDK bootstrap
Solution: ./scripts/deploy.sh --bootstrap
```

#### Insufficient Permissions
```bash
Error: User is not authorized to perform: iam:CreateRole
Solution: Ensure deploying user has required IAM permissions
```

#### Resource Limits
```bash
Error: Cannot exceed quota for resource type
Solution: Request service limit increases or deploy to different region
```

#### Warm Throughput Issues

**Billing Mode Not Enabled:**
```bash
Error: Kinesis On-Demand Advantage billing must be enabled for warm throughput
Solution: ./infrastructure/scripts/demo-manager.sh enable-advantage
```

**Invalid Throughput Value:**
```bash
Error: Invalid warm throughput value. Must be between 1 and 10240 MB/s
Solution: Use throughput value between 1-10240 MB/s
```

**Throughput Scaling in Progress:**
```bash
Status: Stream is scaling to target throughput. This may take a few minutes.
Solution: Wait for scaling to complete, monitor with status command
```

**Region Not Supported:**
```bash
Error: Warm throughput may not be available in this region
Solution: Try a different region or check AWS documentation for availability
```

## Performance Tuning

### Container Resources

- **CPU**: 1-2 vCPUs per 1000 TPS
- **Memory**: 512MB-1GB per container
- **Network**: Ensure sufficient bandwidth for Kinesis API calls

### Batch Optimization

```bash
# Increase batch size for higher throughput
docker run -e KINESIS_BATCH_SIZE=500 kinesis-ondemand-demo

# Reduce batch wait time for lower latency
docker run -e KINESIS_BATCH_WAIT_MS=50 kinesis-ondemand-demo
```

### Scaling Guidelines

| Target TPS | Recommended Containers | CPU per Container | Memory per Container |
|------------|----------------------|-------------------|---------------------|
| 1,000 | 1 | 0.5 vCPU | 512MB |
| 10,000 | 10 | 1 vCPU | 1GB |
| 50,000 | 50 | 1 vCPU | 1GB |

## Cost Optimization

> **💰 COST AWARENESS**: This demo is designed for testing and will generate AWS charges. These optimizations help minimize costs during demo execution, but this should never be used for production cost optimization.

### Resource Right-Sizing

- **ECS Tasks**: Optimized CPU/memory allocation
- **Lambda Functions**: Appropriate memory sizing
- **Kinesis Stream**: On-Demand mode for automatic cost optimization
- **Log Retention**: 7-day retention for cost control

### Auto Scaling

- **ECS Service**: CPU-based auto scaling (1-50 tasks)
- **Kinesis Stream**: Automatic shard scaling
- **Lambda Functions**: Automatic concurrency management

### Cost Monitoring

- Real-time cost calculation and tracking
- Cost comparison with over-provisioned alternatives
- Resource utilization monitoring

## Contributing

### Development Workflow

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/new-component
   ```

2. **Make Changes**
   - Update code
   - Add/update tests
   - Update documentation

3. **Test Changes**
   ```bash
   npm run build
   npm test
   ./build.sh test
   ```

4. **Deploy to Test Environment**
   ```bash
   ./scripts/deploy.sh --environment test --diff
   ```

5. **Create Pull Request**
   - Include test results
   - Document changes
   - Update README if needed

### Code Standards

- **TypeScript**: Strict mode enabled
- **Python**: PEP 8 compliance
- **Testing**: Minimum 80% coverage
- **Documentation**: All public methods documented
- **Linting**: ESLint and pylint configuration enforced

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

### Documentation
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Step Functions Documentation](https://docs.aws.amazon.com/step-functions/)
- [Amazon Kinesis Documentation](https://docs.aws.amazon.com/kinesis/)

### Getting Help
- Check troubleshooting section above
- Review CloudFormation events for deployment issues
- Check AWS service quotas and limits
- Validate IAM permissions

### Reporting Issues
- Include environment details
- Provide error messages and logs
- Include steps to reproduce
- Specify CDK and AWS CLI versions
