# Sentiment Analysis Consumer Lambda Function

This Lambda function consumes social media posts from a Kinesis Data Stream, performs sentiment analysis using Amazon Bedrock Nova Micro, and publishes structured insights to CloudWatch Logs.

## Package Structure

```
lambda/sentiment-consumer/
├── __init__.py                    # Package initialization
├── lambda_handler.py              # Main Lambda entry point
├── deserializer.py                # Kinesis record deserialization
├── batch_processor.py             # Post batching logic
├── sentiment_analyzer.py          # Bedrock sentiment analysis
├── cloudwatch_publisher.py        # CloudWatch Logs publishing
├── models.py                      # Data models
├── serialization.py               # JSON serialization utilities
├── extractors/                    # Insight extraction modules
│   ├── __init__.py
│   ├── product_sentiment.py      # Product sentiment insights
│   ├── trending_topics.py        # Trending topics analysis
│   ├── engagement_correlator.py  # Engagement-sentiment correlation
│   └── geographic_analyzer.py    # Geographic sentiment patterns
├── layer/                         # Lambda Layer dependencies
│   └── requirements.txt           # Python dependencies (boto3, orjson)
└── README.md                      # This file
```

## Dependencies

The Lambda function uses a **Lambda Layer** for dependencies:

- **boto3** (1.34.144): AWS SDK for Python - Bedrock, CloudWatch, Kinesis
- **botocore** (1.34.144): Low-level AWS service access
- **orjson** (3.10.5): Fast JSON parsing library

Additionally, the function uses shared utilities from the project:
- `shared/models.py`: Data models (SocialMediaPost, GeoLocation, etc.)
- `shared/serialization.py`: JSON serialization/deserialization utilities

## Deployment

### CDK Deployment (Recommended and Only Supported Method)

The Lambda function is fully managed by CDK with automatic bundling:

```bash
cd infrastructure
npm install
npm run build
cdk deploy
```

**What CDK Does Automatically:**
1. **Creates Lambda Layer**: Bundles dependencies (boto3, orjson) into a Lambda Layer
2. **Bundles Lambda Code**: Packages Lambda function code with shared utilities
3. **Configures Function**: Sets up runtime, memory, timeout, environment variables
4. **Creates IAM Roles**: Configures permissions for Kinesis, Bedrock, CloudWatch
5. **Sets Up Event Source Mapping**: Connects Lambda to Kinesis stream
6. **Creates Log Groups**: Sets up CloudWatch log groups and streams

**No manual packaging required!** CDK handles everything through its bundling mechanism.

## Configuration

The Lambda function is configured via environment variables (set by CDK):

| Variable | Description | Default |
|----------|-------------|---------|
| `BEDROCK_MODEL_ID` | Bedrock model identifier | `amazon.nova-micro-v1:0` |
| `BEDROCK_REGION` | AWS region for Bedrock API | Same as Lambda region |
| `LOG_GROUP_NAME` | CloudWatch log group name | `/aws/lambda/sentiment-analysis-consumer` |
| `ENVIRONMENT` | Environment name (dev/staging/prod) | `dev` |
| `DEMO_PHASE` | Current demo phase number | `0` |

## Runtime Requirements

- **Runtime**: Python 3.12
- **Memory**: 1024 MB
- **Timeout**: 5 minutes (300 seconds)
- **Architecture**: x86_64 or arm64
- **Layer**: Dependencies layer (automatically created by CDK)

## IAM Permissions Required

The Lambda execution role (created by CDK) includes:

- **Kinesis**: GetRecords, GetShardIterator, DescribeStream, ListShards
- **Bedrock**: InvokeModel for amazon.nova-micro-v1:0
- **CloudWatch Logs**: CreateLogStream, PutLogEvents
- **CloudWatch Metrics**: PutMetricData (namespace: SentimentAnalysis/*)

## Event Source Mapping

Configured automatically by CDK:

- **Batch Size**: 150 records
- **Maximum Batching Window**: 5 seconds
- **Starting Position**: LATEST
- **Batch Item Failures**: Enabled (for partial batch success)
- **Parallelization Factor**: 1

## Local Development

### Testing Lambda Code

```bash
# Run unit tests
cd ../../
python -m pytest tests/ -v

# Test specific module
python -m pytest tests/test_sentiment_analyzer.py -v
```

### Updating Lambda Code

Simply modify the Python files and redeploy with CDK:

```bash
cd infrastructure
cdk deploy
```

CDK will automatically detect changes and update the Lambda function.

## Monitoring

### CloudWatch Metrics

The Lambda function emits custom metrics to `SentimentAnalysis/Consumer`:

- **ErrorRate**: Percentage of failed records
- **ProcessingLatency**: Total processing time in milliseconds
- **BedrockAPICallCount**: Number of Bedrock API calls
- **BedrockAPILatency**: Average Bedrock API latency
- **SuccessfulRecords**: Count of successfully processed records
- **FailedRecords**: Count of failed records

### CloudWatch Logs

Insights are published to multiple log streams:

- `/aws/lambda/sentiment-analysis-consumer-{env}/insights/product-sentiment`
- `/aws/lambda/sentiment-analysis-consumer-{env}/insights/trending-topics`
- `/aws/lambda/sentiment-analysis-consumer-{env}/insights/engagement-sentiment`
- `/aws/lambda/sentiment-analysis-consumer-{env}/insights/geographic-sentiment`

## Troubleshooting

### Common Issues

1. **CDK Bundling Errors**: Ensure Docker is running (CDK uses Docker for bundling)
2. **Import Errors**: Shared utilities are automatically included by CDK bundling
3. **Bedrock Throttling**: Check retry logic and consider increasing batch delay
4. **Memory Issues**: Increase Lambda memory in CDK stack if needed

### Debug Logging

Enable debug logging by modifying the Lambda code:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

Then redeploy with `cdk deploy`.

## Cost Optimization

- Uses **Nova Micro** model for lowest-cost sentiment analysis
- Batches posts to minimize Bedrock API calls (25 posts per call)
- Buffers CloudWatch logs to reduce API calls
- Processes up to 150 records per Lambda invocation
- Dependencies in Lambda Layer (shared across invocations)

## Architecture Benefits

### Lambda Layer Approach

- **Faster Deployments**: Code changes don't require re-uploading dependencies
- **Smaller Packages**: Lambda code package is smaller without dependencies
- **Version Control**: Layer versions can be managed independently
- **Reusability**: Layer can be shared across multiple functions

### CDK Bundling

- **Automatic**: No manual packaging scripts needed
- **Consistent**: Same build process every time
- **Integrated**: Part of normal CDK deployment workflow
- **Docker-based**: Ensures consistent build environment

## Requirements Validation

This package satisfies:
- **Requirement 14.6**: Lambda function code packaging and deployment via CDK
- **Requirement 1.4**: Python 3.12 runtime compatibility
- **Requirement 14.10**: Environment variable configuration through CDK
- **Requirement 14.1**: Lambda function defined as CDK construct
