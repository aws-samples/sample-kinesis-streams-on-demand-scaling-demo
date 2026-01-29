# Sentiment Consumer Lambda Test Data

This document explains the test event structure and provides decoded examples of the social media posts.

## Test Event Structure

The `test-event.json` file contains a Kinesis event with 5 social media posts that demonstrate different sentiment scenarios:

### Record 1: Positive Sentiment - AWS Kinesis
**User**: tech_enthusiast2024  
**Location**: San Francisco, USA  
**Engagement Score**: 8.5  
**Content**: "Just tried the new AWS Kinesis On-Demand feature and it's amazing! 🚀 No more worrying about shard management. Highly recommend! #AWS #Kinesis #CloudComputing"

**Expected Sentiment**: POSITIVE  
**Key Topics**: AWS, Kinesis, CloudComputing  
**Use Case**: Tests positive product sentiment extraction

---

### Record 2: Negative Sentiment - Production Issues
**User**: devops_guru  
**Location**: London, UK  
**Engagement Score**: 3.2  
**Content**: "Warning: Experiencing high latency with our data pipeline today. 🚨 Not sure if it's a Kinesis issue or our consumer app. Need to investigate. #DevOps #ProductionIssues"

**Expected Sentiment**: NEGATIVE  
**Key Topics**: DevOps, ProductionIssues  
**Use Case**: Tests negative sentiment detection and issue identification

---

### Record 3: Positive Sentiment - Bedrock Nova Micro
**User**: cloud_architect  
**Location**: New York, USA  
**Engagement Score**: 9.7  
**Content**: "Loving the new Amazon Bedrock Nova Micro model! 😊 Super fast and cost-effective for sentiment analysis. Perfect for our real-time analytics pipeline. #AIML #Bedrock #Serverless"

**Expected Sentiment**: POSITIVE  
**Key Topics**: AIML, Bedrock, Serverless  
**Mentions**: @aws  
**Use Case**: Tests high engagement positive sentiment with mentions

---

### Record 4: Positive Sentiment - Real-Time Analytics
**User**: data_scientist_2025  
**Location**: Sydney, Australia  
**Engagement Score**: 7.3  
**Content**: "Building a real-time sentiment analysis dashboard using Kinesis + Lambda + Bedrock. The results are incredible! 📈 Processing 100K messages/s with ease. #DataScience #RealTimeAnalytics #AWS"

**Expected Sentiment**: POSITIVE  
**Key Topics**: DataScience, RealTimeAnalytics, AWS  
**Use Case**: Tests technical positive sentiment with performance metrics

---

### Record 5: Positive Sentiment - Cost Optimization
**User**: startup_founder  
**Location**: San Jose, USA  
**Engagement Score**: 6.8  
**Content**: "Our startup just saved 40% on infra costs by switching to Kinesis On-Demand. 💰 No more over-provisioning! Game changer for bootstrapped startups. #StartupLife #CostOptimization #AWS"

**Expected Sentiment**: POSITIVE  
**Key Topics**: StartupLife, CostOptimization, AWS  
**Use Case**: Tests cost-related positive sentiment

---

## How to Use This Test Data

### 1. Test via AWS Lambda Console

1. Navigate to the Lambda function in AWS Console:
   ```
   https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions/sentiment-analysis-consumer-production
   ```

2. Click the "Test" tab

3. Create a new test event:
   - Event name: `KinesisTestEvent`
   - Copy the contents of `test-event.json`
   - Click "Save"

4. Click "Test" to invoke the function

5. Check the results:
   - Execution result shows success/failure
   - CloudWatch Logs for detailed processing logs
   - CloudWatch Insights logs for extracted sentiment data

### 2. Test via AWS CLI

```bash
# Invoke the Lambda function with test event
aws lambda invoke \
  --function-name sentiment-analysis-consumer-production \
  --payload file://test-event.json \
  --region us-east-1 \
  response.json

# View the response
cat response.json
```

### 3. Test Locally (if running locally)

```bash
# Set environment variables
export BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
export BEDROCK_REGION=us-east-1
export LOG_GROUP_NAME=/aws/lambda/sentiment-analysis-consumer-production
export ENVIRONMENT=production

# Run the test
python -c "
import json
from lambda_handler import handler

with open('test-event.json', 'r') as f:
    event = json.load(f)

class MockContext:
    def get_remaining_time_in_millis(self):
        return 300000  # 5 minutes

result = handler(event, MockContext())
print(json.dumps(result, indent=2))
"
```

## Expected Results

### Lambda Response
```json
{
  "batchItemFailures": []
}
```
An empty `batchItemFailures` array indicates all records were processed successfully.

### CloudWatch Metrics
The function should emit the following metrics to `SentimentAnalysis/Consumer` namespace:
- **ErrorRate**: 0% (all records successful)
- **ProcessingLatency**: ~2000-5000ms (depends on Bedrock API latency)
- **BedrockAPICallCount**: 1 (5 posts fit in one batch of 25)
- **BedrockAPILatency**: ~1000-3000ms
- **SuccessfulRecords**: 5
- **FailedRecords**: 0

### CloudWatch Logs Insights
Check the insights log group: `/aws/lambda/sentiment-analysis-consumer-production/insights`

**Product Sentiment Stream** (`product-sentiment`):
```json
{
  "product": "AWS Kinesis",
  "sentiment": "POSITIVE",
  "confidence": 0.95,
  "mention_count": 2
}
```

**Trending Topics Stream** (`trending-topics`):
```json
{
  "topic": "AWS",
  "mention_count": 4,
  "avg_sentiment_score": 0.85,
  "avg_engagement": 7.5
}
```

**Engagement Sentiment Stream** (`engagement-sentiment`):
```json
{
  "correlation": 0.78,
  "high_engagement_positive_ratio": 0.80,
  "avg_positive_engagement": 8.3,
  "avg_negative_engagement": 3.2
}
```

**Geographic Sentiment Stream** (`geographic-sentiment`):
```json
{
  "location": "San Francisco, USA",
  "avg_sentiment_score": 0.90,
  "post_count": 1,
  "avg_engagement": 8.5
}
```

## Decoding the Base64 Data

The `data` field in each Kinesis record is base64-encoded JSON. Here's how to decode it:

### Python
```python
import base64
import json

encoded_data = "eyJpZCI6ICJwb3N0XzEyMzQ1Njc4IiwgInRpbWVzdGFtcCI6..."
decoded_bytes = base64.b64decode(encoded_data)
post_data = json.loads(decoded_bytes.decode('utf-8'))
print(json.dumps(post_data, indent=2))
```

### Bash
```bash
echo "eyJpZCI6ICJwb3N0XzEyMzQ1Njc4IiwgInRpbWVzdGFtcCI6..." | base64 -d | jq .
```

## Troubleshooting

### Issue: Lambda times out
**Solution**: The test event has 5 records which should process quickly. If timing out:
- Check Bedrock API latency in CloudWatch metrics
- Verify Lambda has 1024MB memory and 5-minute timeout
- Check VPC configuration if Lambda is in a VPC

### Issue: Bedrock API errors
**Solution**: 
- Verify the Lambda role has `bedrock:InvokeModel` permission
- Confirm Nova Micro model is available in your region
- Check Bedrock service quotas

### Issue: No insights in CloudWatch Logs
**Solution**:
- Verify log group `/aws/lambda/sentiment-analysis-consumer-production/insights` exists
- Check Lambda role has `logs:PutLogEvents` permission
- Review Lambda execution logs for errors

### Issue: High error rate
**Solution**:
- Check Lambda execution logs for specific error messages
- Verify all dependencies are bundled correctly
- Test with a single record first to isolate issues

## Modifying Test Data

To create your own test data:

1. Create a social media post JSON:
```json
{
  "id": "post_custom123",
  "timestamp": "2025-01-29T12:00:00.000000Z",
  "user_id": "user_test123",
  "username": "test_user",
  "content": "Your test content here #TestHashtag",
  "hashtags": ["TestHashtag"],
  "mentions": [],
  "location": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "city": "New York",
    "country": "USA"
  },
  "engagement_score": 5.0,
  "post_type": "original"
}
```

2. Base64 encode it:
```python
import base64
import json

post = {...}  # Your post JSON
encoded = base64.b64encode(json.dumps(post).encode('utf-8')).decode('utf-8')
print(encoded)
```

3. Add it to the Kinesis event structure in `test-event.json`

## Performance Benchmarks

Expected performance with this test data:
- **Total Processing Time**: 2-5 seconds
- **Bedrock API Latency**: 1-3 seconds per batch
- **Deserialization Time**: <100ms
- **Insight Extraction Time**: <500ms
- **CloudWatch Publishing Time**: <1 second

## Next Steps

After successful testing:
1. Monitor CloudWatch Logs for detailed execution traces
2. Check CloudWatch Metrics dashboard for performance metrics
3. Review CloudWatch Insights logs for extracted sentiment data
4. Test with larger batches (up to 150 records per invocation)
5. Test error scenarios by including malformed records
