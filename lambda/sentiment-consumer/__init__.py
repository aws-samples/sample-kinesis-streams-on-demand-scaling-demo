"""
Sentiment Analysis Consumer Lambda Function.

This Lambda function consumes social media posts from Kinesis Data Stream,
analyzes sentiment using Amazon Bedrock Nova Micro, and publishes insights
to CloudWatch Logs for dashboard visualization.
"""

__version__ = "1.0.0"
