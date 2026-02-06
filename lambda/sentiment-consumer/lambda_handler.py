"""
Lambda handler for sentiment analysis consumer.

This module provides the main entry point for the Lambda function that processes
Kinesis stream records, performs sentiment analysis using Amazon Bedrock, extracts
insights, and publishes results to CloudWatch Logs.
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

# Import local modules
from deserializer import RecordDeserializer
from sentiment_analyzer import SentimentAnalyzer
from cloudwatch_publisher import CloudWatchPublisher
from models import BatchProcessingMetrics

# Import extractors
from extractors.product_sentiment import ProductSentimentExtractor
from extractors.trending_topics import TrendingTopicsExtractor
from extractors.engagement_correlator import EngagementSentimentCorrelator
from extractors.geographic_analyzer import GeographicSentimentAnalyzer

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients (reused across invocations)
bedrock_client = None
cloudwatch_metrics_client = None


def get_bedrock_client():
    """Get or create Bedrock Runtime client."""
    global bedrock_client
    if bedrock_client is None:
        bedrock_region = os.environ.get('BEDROCK_REGION', 'us-east-1')
        bedrock_client = boto3.client('bedrock-runtime', region_name=bedrock_region)
    return bedrock_client
def get_cloudwatch_metrics_client():
    """Get or create CloudWatch Metrics client."""
    global cloudwatch_metrics_client
    if cloudwatch_metrics_client is None:
        cloudwatch_metrics_client = boto3.client('cloudwatch')
    return cloudwatch_metrics_client


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for sentiment analysis consumer.
    
    This function processes Kinesis stream records by:
    1. Deserializing records into SocialMediaPost objects
    2. Analyzing sentiment using Amazon Bedrock Nova Micro (single API call)
    3. Extracting insights across multiple dimensions
    4. Publishing insights to CloudWatch Metrics
    5. Emitting processing metrics
    
    Args:
        event: Kinesis event with Records array (batched by event source mapper)
        context: Lambda context object with runtime information
        
    Returns:
        Response dictionary with batchItemFailures for retry
        
    Requirements: 1.3, 2.3, 2.6, 10.4, 10.5, 12.5
    """
    start_time = time.time()
    batch_id = str(uuid.uuid4())
    
    logger.info(f"Starting sentiment analysis batch processing. Batch ID: {batch_id}")
    
    # Extract configuration from environment
    model_id = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')
    demo_phase = int(os.environ.get('DEMO_PHASE', '0'))
    environment = os.environ.get('ENVIRONMENT', 'dev')
    
    # Initialize components
    deserializer = RecordDeserializer()
    sentiment_analyzer = SentimentAnalyzer(get_bedrock_client(), model_id=model_id)
    cloudwatch_publisher = CloudWatchPublisher(
        metrics_client=get_cloudwatch_metrics_client(),
        environment=environment,
        demo_phase=demo_phase,
        batch_id=batch_id
    )
    
    # Initialize extractors
    product_extractor = ProductSentimentExtractor()
    topics_extractor = TrendingTopicsExtractor(trending_threshold=10)
    engagement_correlator = EngagementSentimentCorrelator()
    geographic_analyzer = GeographicSentimentAnalyzer()
    
    # Track processing metrics
    total_records = len(event.get('Records', []))
    successful_records = 0
    failed_records = 0
    failed_sequence_numbers = []
    bedrock_total_latency_ms = 0.0
    
    try:
        # Step 1: Deserialize all records
        logger.info(f"Deserializing {total_records} records")
        posts = []
        post_to_sequence = {}  # Map post_id to sequence number for failure tracking
        
        for record in event.get('Records', []):
            kinesis_data = record.get('kinesis', {})
            sequence_number = kinesis_data.get('sequenceNumber')
            
            post = deserializer.deserialize_record(record)
            
            if post is not None:
                posts.append(post)
                post_to_sequence[post.id] = sequence_number
            else:
                # Deserialization failed, track for retry
                failed_records += 1
                if sequence_number:
                    failed_sequence_numbers.append(sequence_number)
                logger.warning(f"Failed to deserialize record: {sequence_number}")
        
        logger.info(f"Successfully deserialized {len(posts)} posts, {failed_records} failures")
        
        if not posts:
            logger.warning("No posts to process after deserialization")
            return _create_response(failed_sequence_numbers)
        
        # Step 2: Randomly sample 20 posts for sentiment analysis
        # This ensures consistent Bedrock performance regardless of batch size
        import random
        sample_size = min(20, len(posts))
        sampled_posts = random.sample(posts, sample_size)
        
        logger.info(
            f"Randomly sampled {sample_size} posts from {len(posts)} total posts for sentiment analysis"
        )
        
        # Step 3: Analyze sentiment with single Bedrock API call
        logger.info(f"Analyzing sentiment for {sample_size} posts with single Bedrock API call")
        
        try:
            bedrock_start = time.time()
            sentiment_results = sentiment_analyzer.analyze_batch(sampled_posts)
            bedrock_total_latency_ms = (time.time() - bedrock_start) * 1000
            
            successful_records += len(sentiment_results)
            
            logger.info(
                f"Bedrock analysis completed in {bedrock_total_latency_ms:.2f}ms. "
                f"Got {len(sentiment_results)} sentiment results from {sample_size} sampled posts."
            )
            
        except Exception as e:
            logger.error(f"Failed to analyze sentiment: {e}", exc_info=True)
            # Mark all posts as failed
            for post in posts:
                seq_num = post_to_sequence.get(post.id)
                if seq_num and seq_num not in failed_sequence_numbers:
                    failed_sequence_numbers.append(seq_num)
                    failed_records += 1
            
            # Return early with failures
            total_processing_time_ms = (time.time() - start_time) * 1000
            emit_processing_metrics(
                environment=environment,
                total_records=total_records,
                successful_records=0,
                failed_records=failed_records,
                bedrock_api_calls=0,
                bedrock_total_latency_ms=0.0,
                total_processing_time_ms=total_processing_time_ms
            )
            return _create_response(failed_sequence_numbers)
        
        if not sentiment_results:
            logger.warning("No sentiment results generated")
            return _create_response(failed_sequence_numbers)
        
        # Step 4: Extract insights and publish metrics
        # Use sampled posts for insight extraction to match sentiment results
        logger.info("Extracting insights from sentiment results")
        
        try:
            # Product sentiment insights
            product_insights = product_extractor.extract_insights(sampled_posts, sentiment_results)
            logger.info(f"Extracted {len(product_insights)} product insights")
            
            # Trending topics insights
            topic_insights = topics_extractor.extract_insights(sampled_posts, sentiment_results)
            logger.info(f"Extracted {len(topic_insights)} topic insights")
            
            # Engagement-sentiment correlation
            engagement_insight = engagement_correlator.extract_insights(sampled_posts, sentiment_results)
            logger.info("Extracted engagement-sentiment correlation insight")
            
            # Geographic sentiment insights
            geographic_insights = geographic_analyzer.extract_insights(sampled_posts, sentiment_results)
            logger.info(f"Extracted {len(geographic_insights)} geographic insights")
            
            # Publish aggregated metrics to CloudWatch Metrics for dashboards
            insights_dict = {
                'product_insights': product_insights,
                'topic_insights': topic_insights,
                'engagement_insight': engagement_insight,
                'geographic_insights': geographic_insights
            }
            cloudwatch_publisher.publish_metrics(insights_dict, len(sampled_posts), sentiment_results)
            logger.info("Published insight metrics to CloudWatch")
            
        except Exception as e:
            logger.error(f"Failed to extract insights: {e}", exc_info=True)
        
        # Step 5: Emit processing metrics
        total_processing_time_ms = (time.time() - start_time) * 1000
        
        try:
            emit_processing_metrics(
                environment=environment,
                total_records=total_records,
                successful_records=successful_records,
                failed_records=failed_records,
                bedrock_api_calls=1,  # Single API call per Lambda invocation
                bedrock_total_latency_ms=bedrock_total_latency_ms,
                total_processing_time_ms=total_processing_time_ms
            )
            logger.info("Successfully emitted processing metrics")
        except Exception as e:
            logger.error(f"Failed to emit metrics: {e}", exc_info=True)
        
        # Log final summary
        logger.info(
            f"Batch processing complete. Batch ID: {batch_id}, "
            f"Total: {total_records}, Success: {successful_records}, "
            f"Failed: {failed_records}, Duration: {total_processing_time_ms:.2f}ms"
        )
        
        return _create_response(failed_sequence_numbers)
        
    except Exception as e:
        logger.error(f"Unexpected error in Lambda handler: {e}", exc_info=True)
        
        # Try to emit error metrics
        try:
            total_processing_time_ms = (time.time() - start_time) * 1000
            emit_processing_metrics(
                environment=environment,
                total_records=total_records,
                successful_records=successful_records,
                failed_records=total_records,  # Mark all as failed
                bedrock_api_calls=0,
                bedrock_total_latency_ms=bedrock_total_latency_ms,
                total_processing_time_ms=total_processing_time_ms
            )
        except:
            pass
        
        # Return all records as failed for retry
        all_sequence_numbers = [
            record.get('kinesis', {}).get('sequenceNumber')
            for record in event.get('Records', [])
            if record.get('kinesis', {}).get('sequenceNumber')
        ]
        return _create_response(all_sequence_numbers)


def _create_response(failed_sequence_numbers: List[str]) -> Dict[str, Any]:
    """
    Create Lambda response with batch item failures.
    
    Args:
        failed_sequence_numbers: List of Kinesis sequence numbers that failed
        
    Returns:
        Response dictionary for Lambda
    """
    if not failed_sequence_numbers:
        return {"batchItemFailures": []}
    
    return {
        "batchItemFailures": [
            {"itemIdentifier": seq_num}
            for seq_num in failed_sequence_numbers
        ]
    }


def emit_processing_metrics(
    environment: str,
    total_records: int,
    successful_records: int,
    failed_records: int,
    bedrock_api_calls: int,
    bedrock_total_latency_ms: float,
    total_processing_time_ms: float
) -> None:
    """
    Emit CloudWatch metrics for batch processing.
    
    Emits metrics for:
    - Error rate (failed_records / total_records)
    - Processing latency (total_processing_time_ms)
    - Bedrock API call count
    - Bedrock API latency
    
    Args:
        environment: Environment name (for metric dimensions)
        total_records: Total number of records processed
        successful_records: Number of successfully processed records
        failed_records: Number of failed records
        bedrock_api_calls: Number of Bedrock API calls made
        bedrock_total_latency_ms: Total time spent in Bedrock API calls
        total_processing_time_ms: Total processing time for the batch
        
    Requirements: 10.4, 12.5
    """
    try:
        metrics_client = get_cloudwatch_metrics_client()
        
        # Calculate error rate
        error_rate = (failed_records / total_records * 100) if total_records > 0 else 0.0
        
        # Calculate average Bedrock latency
        avg_bedrock_latency_ms = (
            bedrock_total_latency_ms / bedrock_api_calls
            if bedrock_api_calls > 0 else 0.0
        )
        
        # Prepare metric data
        metric_data = [
            {
                'MetricName': 'ErrorRate',
                'Value': error_rate,
                'Unit': 'Percent',
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': environment},
                    {'Name': 'Component', 'Value': 'SentimentAnalysis'}
                ]
            },
            {
                'MetricName': 'ProcessingLatency',
                'Value': total_processing_time_ms,
                'Unit': 'Milliseconds',
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': environment},
                    {'Name': 'Component', 'Value': 'SentimentAnalysis'}
                ]
            },
            {
                'MetricName': 'BedrockAPICallCount',
                'Value': bedrock_api_calls,
                'Unit': 'Count',
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': environment},
                    {'Name': 'Component', 'Value': 'SentimentAnalysis'}
                ]
            },
            {
                'MetricName': 'BedrockAPILatency',
                'Value': avg_bedrock_latency_ms,
                'Unit': 'Milliseconds',
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': environment},
                    {'Name': 'Component', 'Value': 'SentimentAnalysis'}
                ]
            },
            {
                'MetricName': 'SuccessfulRecords',
                'Value': successful_records,
                'Unit': 'Count',
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': environment},
                    {'Name': 'Component', 'Value': 'SentimentAnalysis'}
                ]
            },
            {
                'MetricName': 'FailedRecords',
                'Value': failed_records,
                'Unit': 'Count',
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': environment},
                    {'Name': 'Component', 'Value': 'SentimentAnalysis'}
                ]
            }
        ]
        
        # Put metrics to CloudWatch
        metrics_client.put_metric_data(
            Namespace='SentimentAnalysis/Consumer',
            MetricData=metric_data
        )
        
        logger.info(
            f"Emitted metrics: ErrorRate={error_rate:.2f}%, "
            f"ProcessingLatency={total_processing_time_ms:.2f}ms, "
            f"BedrockAPICalls={bedrock_api_calls}, "
            f"BedrockLatency={avg_bedrock_latency_ms:.2f}ms"
        )
        
    except Exception as e:
        logger.error(f"Failed to emit CloudWatch metrics: {e}", exc_info=True)
        # Don't raise - metrics emission failure shouldn't fail the Lambda
