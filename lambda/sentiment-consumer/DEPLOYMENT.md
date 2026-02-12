# Lambda Deployment Guide

This guide provides instructions for deploying the Sentiment Analysis Consumer Lambda function using AWS CDK.

## Prerequisites

- Python 3.12 installed locally (for development/testing)
- Node.js and npm installed (for CDK)
- AWS CLI configured with appropriate credentials
- Docker installed and running (required for CDK bundling)
- Access to AWS account with Lambda, Bedrock, Kinesis, and CloudWatch permissions

## Deployment Architecture

The Lambda function uses a **modern CDK-based deployment** with:

1. **Lambda Layer**: Dependencies (boto3, orjson) packaged as a reusable layer
2. **Inline Code**: Lambda function code bundled automatically by CDK
3. **Automatic Bundling**: CDK handles all packaging using Docker
4. **Shared Utilities**: Project's shared modules included automatically

**No manual packaging scripts required!**

## Deployment Method: CDK Only

### Step 1: Install CDK Dependencies

```bash
cd infrastructure
npm install
```

### Step 2: Build the CDK Stack

```bash
npm run build
```

This compiles the TypeScript CDK code to JavaScript.

### Step 3: Deploy the Stack

```bash
cdk deploy
```

**What happens during deployment:**

1. **Layer Creation**: CDK bundles dependencies into a Lambda Layer
   - Runs `pip install` in Docker container
   - Creates layer with boto3, botocore, orjson
   - Uploads layer to AWS

2. **Code Bundling**: CDK bundles Lambda function code
   - Copies all Lambda Python files
   - Includes shared utilities (models.py, serialization.py)
   - Excludes unnecessary files (tests, docs, build artifacts)
   - Creates deployment package

3. **Resource Creation**: CDK creates/updates AWS resources
   - Lambda function with layer attached
   - IAM roles and policies
   - Event Source Mapping to Kinesis
   - CloudWatch Log Groups and Streams
   - Tags and outputs

4. **Configuration**: CDK sets environment variables and configuration
   - Bedrock model ID and region
   - Log group names
   - Environment name

### Step 4: Verify Deployment

```bash
# Check Lambda function
aws lambda get-function --function-name sentiment-analysis-consumer-dev

# Check Event Source Mapping
aws lambda list-event-source-mappings \
  --function-name sentiment-analysis-consumer-dev

# View CDK outputs
cdk outputs
```

## Updating the Lambda Function

### Code Changes Only

Simply modify the Python files and redeploy:

```bash
cd infrastructure
cdk deploy
```

CDK automatically detects changes and updates only what's necessary.

### Dependency Changes

Update `lambda/sentiment-consumer/layer/requirements.txt` and redeploy:

```bash
cd infrastructure
cdk deploy
```

CDK will rebuild the layer with new dependencies.

### Configuration Changes

Modify the CDK stack (`infrastructure/src/kinesis-ondemand-demo-stack.ts`) and redeploy:

```bash
cd infrastructure
npm run build
cdk deploy
```

## Development Workflow

### 1. Make Code Changes

Edit Lambda function files in `lambda/sentiment-consumer/`:
- `lambda_handler.py`
- `sentiment_analyzer.py`
- `cloudwatch_publisher.py`
- etc.

### 2. Test Locally (Optional)

```bash
# Run unit tests
python -m pytest tests/ -v

# Test specific functionality
python -m pytest tests/test_sentiment_analyzer.py -v
```

### 3. Deploy with CDK

```bash
cd infrastructure
cdk deploy
```

### 4. Monitor Deployment

```bash
# Watch CloudWatch Logs
aws logs tail /aws/lambda/sentiment-analysis-consumer-dev --follow

# Check metrics
aws cloudwatch get-metric-statistics \
  --namespace SentimentAnalysis/Consumer \
  --metric-name ProcessingLatency \
  --dimensions Name=Environment,Value=dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Post-Deployment Verification

### 1. Check Lambda Function Status

```bash
aws lambda get-function --function-name sentiment-analysis-consumer-dev
```

Expected output:
- State: Active
- Runtime: python3.12
- Memory: 1024 MB
- Timeout: 300 seconds
- Layers: 1 layer attached

### 2. Verify Event Source Mapping

```bash
aws lambda list-event-source-mappings \
  --function-name sentiment-analysis-consumer-dev
```

Expected output:
- State: Enabled
- BatchSize: 150
- MaximumBatchingWindowInSeconds: 5

### 3. Check CloudWatch Log Groups

```bash
aws logs describe-log-groups \
  --log-group-name-prefix /aws/lambda/sentiment-analysis-consumer
```

Expected log groups:
- `/aws/lambda/sentiment-analysis-consumer-dev`
- `/aws/lambda/sentiment-analysis-consumer-dev/insights`

### 4. Monitor Lambda Invocations

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=sentiment-analysis-consumer-dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## Troubleshooting

### Issue: CDK bundling fails

**Cause**: Docker not running or not accessible

**Solution**:
```bash
# Start Docker
# On macOS: Open Docker Desktop
# On Linux: sudo systemctl start docker

# Verify Docker is running
docker ps
```

### Issue: Layer creation fails

**Cause**: Dependencies can't be installed

**Solution**:
```bash
# Check requirements.txt syntax
cat lambda/sentiment-consumer/layer/requirements.txt

# Test locally
pip install -r lambda/sentiment-consumer/layer/requirements.txt
```

### Issue: Import errors in Lambda

**Cause**: Shared utilities not included

**Solution**: CDK bundling command automatically includes shared utilities. Verify the bundling command in `kinesis-ondemand-demo-stack.ts`:

```typescript
'cp /asset-input/../../shared/__init__.py /asset-output/shared/ && ' +
'cp /asset-input/../../shared/models.py /asset-output/shared/ && ' +
'cp /asset-input/../../shared/serialization.py /asset-output/shared/'
```

### Issue: Bedrock permission denied

**Cause**: IAM role missing Bedrock permissions

**Solution**: CDK automatically creates the role. Verify in AWS Console or:

```bash
aws iam get-role-policy \
  --role-name KinesisDemo-SentimentConsumerRole-dev \
  --policy-name BedrockAccess
```

### Issue: Function not triggered by Kinesis

**Cause**: Event Source Mapping not enabled or stream doesn't exist

**Solution**:
```bash
# Check if stream exists
aws kinesis describe-stream --stream-name social-media-stream-dev

# Check Event Source Mapping
aws lambda list-event-source-mappings \
  --function-name sentiment-analysis-consumer-dev
```

## Rollback

### Rollback to Previous Version

```bash
cd infrastructure
git checkout <previous-commit>
npm run build
cdk deploy
```

### Rollback Using CDK

CDK doesn't have built-in rollback, but you can:

1. Revert code changes in git
2. Redeploy with `cdk deploy`

## Monitoring After Deployment

### View Lambda Logs

```bash
# Main Lambda logs
aws logs tail /aws/lambda/sentiment-analysis-consumer-dev --follow

# Insight logs
aws logs tail /aws/lambda/sentiment-analysis-consumer-dev/insights/product-sentiment --follow
```

### Check Custom Metrics

```bash
# Error rate
aws cloudwatch get-metric-statistics \
  --namespace SentimentAnalysis/Consumer \
  --metric-name ErrorRate \
  --dimensions Name=Environment,Value=dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average

# Processing latency
aws cloudwatch get-metric-statistics \
  --namespace SentimentAnalysis/Consumer \
  --metric-name ProcessingLatency \
  --dimensions Name=Environment,Value=dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

### View CDK Outputs

```bash
cd infrastructure
cdk outputs
```

This shows:
- Lambda function ARN
- Log group names
- Dashboard URL
- Other resource identifiers

## Cost Estimation

Estimated costs for the Lambda function (per month):

- **Lambda Invocations**: ~$0.20 per 1M requests
- **Lambda Duration**: ~$0.0000166667 per GB-second
- **Lambda Layer Storage**: ~$0.03 per GB-month
- **Bedrock API Calls**: ~$0.00015 per 1K input tokens (Nova Micro)
- **CloudWatch Logs**: ~$0.50 per GB ingested
- **CloudWatch Metrics**: ~$0.30 per custom metric

Example: Processing 1M posts/month with 1024 MB Lambda:
- Lambda: ~$5
- Bedrock: ~$15
- CloudWatch: ~$10
- **Total**: ~$30/month

## Benefits of CDK Deployment

### 1. No Manual Packaging
- No shell scripts to maintain
- No manual ZIP file creation
- No dependency management headaches

### 2. Consistent Builds
- Docker-based bundling ensures consistency
- Same build process every time
- No "works on my machine" issues

### 3. Infrastructure as Code
- All resources defined in code
- Version controlled
- Repeatable deployments

### 4. Automatic Optimization
- CDK excludes unnecessary files
- Optimizes layer and code packages
- Handles dependencies efficiently

### 5. Integrated Workflow
- Single command deployment
- Automatic resource updates
- Built-in dependency tracking

## Security Considerations

1. **IAM Permissions**: CDK creates least-privilege roles automatically
2. **Environment Variables**: No secrets in environment variables (use Secrets Manager if needed)
3. **VPC Configuration**: Consider VPC deployment for enhanced security
4. **Encryption**: Enable encryption at rest for CloudWatch Logs
5. **Access Logging**: CloudTrail logs all Lambda API calls

## Support

For issues or questions:
1. Check CloudWatch Logs for error messages
2. Review the README.md for configuration details
3. Consult the design document at `.kiro/specs/sentiment-analysis-consumer/design.md`
4. Check CDK documentation: https://docs.aws.amazon.com/cdk/

## Quick Reference

```bash
# Deploy everything
cd infrastructure && cdk deploy

# Update Lambda code only
cd infrastructure && cdk deploy

# View logs
aws logs tail /aws/lambda/sentiment-analysis-consumer-dev --follow

# Check function status
aws lambda get-function --function-name sentiment-analysis-consumer-dev

# View CDK outputs
cd infrastructure && cdk outputs
```
