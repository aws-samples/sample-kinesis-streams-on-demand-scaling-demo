# Token Tracking Implementation Summary

## Status: ✅ READY TO DEPLOY

All code changes have been implemented to enable token usage monitoring for the Sentiment Analysis Lambda function.

## Changes Made

### 1. Lambda Code Updates

#### `sentiment_analyzer.py`
- **Added import**: `from token_metrics import TokenMetricsTracker`
- **Updated `__init__` method**: 
  - Added `cloudwatch_client` parameter
  - Added `environment` parameter
  - Initialized `TokenMetricsTracker` instance
- **Updated `analyze_batch` method**:
  - Moved duration calculation before parsing response
  - Added `self.token_tracker.track_batch()` call after Bedrock API response
  - Tracks token usage, logs it, and publishes CloudWatch metrics
- **Added new methods**:
  - `get_invocation_summary()`: Returns cumulative token usage for the Lambda invocation
  - `log_invocation_summary()`: Logs the token usage summary

#### `lambda_handler.py`
- **Updated `SentimentAnalyzer` initialization**:
  - Now passes `cloudwatch_client=get_cloudwatch_metrics_client()`
  - Now passes `environment=environment`
- **Added token summary logging**:
  - Calls `sentiment_analyzer.log_invocation_summary()` after processing all batches
  - Wrapped in try-except to prevent failures from affecting Lambda execution

### 2. CDK Infrastructure Updates

#### `kinesis-ondemand-demo-stack.ts`
- **Updated Lambda bundling command**:
  - Added verification step to check `token_metrics.py` is included
  - Increased output lines from 20 to 30 for better visibility
  - Added explicit check: `ls -la /asset-output/token_metrics.py`

The bundling already copies all `.py` files from `lambda/sentiment-consumer/`, so `token_metrics.py` will be included automatically.

## What Gets Tracked

### Per-Batch Metrics (logged and published to CloudWatch)
- **Input Tokens**: Number of tokens in the prompt
- **Output Tokens**: Number of tokens in the response
- **Total Tokens**: Sum of input and output tokens
- **Tokens Per Post**: Average tokens per social media post
- **Duration**: API call duration in milliseconds
- **Cost**: Estimated cost in USD (input + output)

### Invocation Summary (logged at end of Lambda execution)
- **Total Input Tokens**: Cumulative across all batches
- **Total Output Tokens**: Cumulative across all batches
- **Total Tokens**: Sum of all tokens
- **Total API Calls**: Number of Bedrock API calls made
- **Total Posts Analyzed**: Number of posts processed
- **Average Tokens Per Post**: Overall average
- **Total Cost**: Cumulative estimated cost in USD

## CloudWatch Metrics Published

All metrics are published to the `SentimentAnalysis/Bedrock` namespace with dimensions:
- `Environment`: e.g., "production", "dev"
- `ModelId`: e.g., "amazon.nova-micro-v1:0"

### Metric Names
1. `InputTokens` (Count)
2. `OutputTokens` (Count)
3. `TotalTokens` (Count)
4. `TokensPerPost` (Count)
5. `BedrockAPILatency` (Milliseconds)
6. `BedrockCost` (None - represents USD)

## Example Log Output

### Per-Batch Log
```
Bedrock API token usage: Input tokens: 1234, Output tokens: 567, Total tokens: 1801, Posts analyzed: 25, Tokens per post: 72.04, Duration: 731.59ms, Estimated cost: $0.000122
```

### Invocation Summary Log
```
Lambda invocation token summary: Total tokens: 5403 (Input: 3702, Output: 1701), API calls: 3, Posts analyzed: 75, Avg tokens/post: 72.04, Total cost: $0.000368
```

## Pricing Reference

**Amazon Nova Micro Pricing** (as of implementation):
- Input tokens: $0.035 per 1M tokens
- Output tokens: $0.14 per 1M tokens

## Next Steps

### 1. Deploy the Updated Lambda Function
```bash
cd infrastructure
npm run deploy -- --no-approval
```

This will:
- Bundle the Lambda code including `token_metrics.py`
- Update the Lambda function with token tracking enabled
- Deploy the changes to AWS

### 2. Test Token Tracking
```bash
# Invoke the Lambda with test data
aws lambda invoke \
  --function-name sentiment-analysis-consumer-production \
  --payload file://lambda/sentiment-consumer/test-event.json \
  --region us-east-1 \
  response.json

# Check the logs for token usage
aws logs tail /aws/lambda/sentiment-analysis-consumer-production \
  --follow \
  --region us-east-1
```

### 3. Verify CloudWatch Metrics
```bash
# List available metrics
aws cloudwatch list-metrics \
  --namespace "SentimentAnalysis/Bedrock" \
  --region us-east-1

# Get token usage for the last hour
aws cloudwatch get-metric-statistics \
  --namespace "SentimentAnalysis/Bedrock" \
  --metric-name TotalTokens \
  --dimensions Name=Environment,Value=production Name=ModelId,Value=amazon.nova-micro-v1:0 \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum Average \
  --region us-east-1
```

### 4. Create CloudWatch Dashboard (Optional)
After deployment, you can create a dashboard to visualize token usage:
- Token usage over time
- Cost trends
- Tokens per post efficiency
- API latency correlation with token count

### 5. Set Up CloudWatch Alarms (Optional)
Create alarms for:
- High token usage (e.g., > 1M tokens per hour)
- High cost (e.g., > $1 per hour)
- Unusual tokens per post (e.g., > 200 tokens/post)

## Troubleshooting

### If token metrics don't appear in CloudWatch:
1. Check Lambda logs for errors in `track_batch()` calls
2. Verify IAM permissions for `cloudwatch:PutMetricData`
3. Check the namespace filter in IAM policy: `SentimentAnalysis/*`

### If token counts are 0:
1. Verify Bedrock response includes `usage` field
2. Check `extract_token_usage()` method is parsing correctly
3. Enable debug logging: `logger.setLevel(logging.DEBUG)`

### If costs seem incorrect:
1. Verify pricing constants in `token_metrics.py`:
   - `INPUT_TOKEN_PRICE = 0.035` (per 1M tokens)
   - `OUTPUT_TOKEN_PRICE = 0.14` (per 1M tokens)
2. Check AWS pricing page for latest Nova Micro rates

## Files Modified

1. `lambda/sentiment-consumer/sentiment_analyzer.py` - Added token tracking
2. `lambda/sentiment-consumer/lambda_handler.py` - Integrated token tracker
3. `infrastructure/src/kinesis-ondemand-demo-stack.ts` - Updated bundling
4. `lambda/sentiment-consumer/token_metrics.py` - Already created (no changes needed)

## Files to Review

- `lambda/sentiment-consumer/TOKEN_MONITORING.md` - Comprehensive monitoring guide
- `lambda/sentiment-consumer/QUICK_TOKEN_MONITORING.md` - Quick reference commands
- `lambda/sentiment-consumer/token_metrics.py` - Token tracking implementation
