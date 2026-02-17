"""
CloudWatch Publisher for sentiment analysis insights.

This module handles publishing metrics to CloudWatch Metrics for dashboard visualization.
"""

import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime


class CloudWatchPublisher:
    """
    Publishes sentiment insights to CloudWatch Metrics for dashboard visualization.
    """
    
    def __init__(
        self,
        metrics_client,
        environment: str = 'production',
        demo_phase: Optional[int] = None,
        batch_id: Optional[str] = None,
    ):
        """
        Initialize CloudWatch publisher.
        
        Args:
            metrics_client: boto3 CloudWatch Metrics client
            environment: Environment name for metric dimensions
            demo_phase: Current demo phase number (for metadata)
            batch_id: Unique identifier for this processing batch
        """
        self.metrics_client = metrics_client
        self.environment = environment
        self.demo_phase = demo_phase or 0
        self.batch_id = batch_id or str(uuid.uuid4())
    
    def publish_metrics(
        self,
        insights: Dict[str, Any],
        posts_count: int,
        sentiment_results: List[Any]
    ) -> None:
        """
        Publish aggregated metrics to CloudWatch Metrics for dashboard visualization.
        
        Args:
            insights: Dictionary containing all extracted insights
            posts_count: Total number of posts processed
            sentiment_results: List of sentiment results
        """
        if not self.metrics_client:
            return
        
        def sanitize_dimension_value(value: str) -> str:
            """
            Sanitize dimension value for CloudWatch (ASCII only, max 255 chars).
            
            Args:
                value: Original dimension value
                
            Returns:
                Sanitized ASCII-only string
            """
            # Remove non-ASCII characters
            ascii_value = value.encode('ascii', 'ignore').decode('ascii')
            # Truncate to CloudWatch limit
            return ascii_value[:255] if ascii_value else 'unknown'
        
        try:
            from datetime import datetime
            
            metric_data = []
            timestamp = datetime.utcnow()
            
            # Calculate sentiment distribution
            positive_count = sum(1 for r in sentiment_results if r.sentiment == 'positive')
            negative_count = sum(1 for r in sentiment_results if r.sentiment == 'negative')
            neutral_count = sum(1 for r in sentiment_results if r.sentiment == 'neutral')
            
            avg_sentiment_score = sum(r.sentiment_score for r in sentiment_results) / len(sentiment_results) if sentiment_results else 0
            avg_confidence = sum(r.confidence for r in sentiment_results) / len(sentiment_results) if sentiment_results else 0
            
            # Sentiment distribution metrics
            metric_data.extend([
                {
                    'MetricName': 'PositivePosts',
                    'Value': positive_count,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                },
                {
                    'MetricName': 'NegativePosts',
                    'Value': negative_count,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                },
                {
                    'MetricName': 'NeutralPosts',
                    'Value': neutral_count,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                },
                {
                    'MetricName': 'AverageSentimentScore',
                    'Value': avg_sentiment_score,
                    'Unit': 'None',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                },
                {
                    'MetricName': 'AverageConfidence',
                    'Value': avg_confidence,
                    'Unit': 'None',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                }
            ])
            
            # Product sentiment metrics (top products)
            if 'product_insights' in insights and insights['product_insights']:
                for insight in insights['product_insights'][:10]:  # Top 10 products
                    metric_data.append({
                        'MetricName': 'ProductSentiment',
                        'Value': insight.average_sentiment,
                        'Unit': 'None',
                        'Timestamp': timestamp,
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment},
                            {'Name': 'Product', 'Value': sanitize_dimension_value(insight.product_name)}
                        ]
                    })
            
            # Trending topics metrics
            if 'topic_insights' in insights and insights['topic_insights']:
                trending_count = sum(1 for t in insights['topic_insights'] if t.is_trending)
                metric_data.append({
                    'MetricName': 'TrendingTopicsCount',
                    'Value': trending_count,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                })
                
                # Top hashtags by post count
                for insight in insights['topic_insights'][:10]:
                    metric_data.append({
                        'MetricName': 'HashtagPostCount',
                        'Value': insight.post_count,
                        'Unit': 'Count',
                        'Timestamp': timestamp,
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment},
                            {'Name': 'Hashtag', 'Value': sanitize_dimension_value(insight.hashtag)}
                        ]
                    })
            
            # Engagement-sentiment correlation
            if 'engagement_insight' in insights and insights['engagement_insight']:
                eng_insight = insights['engagement_insight']
                metric_data.append({
                    'MetricName': 'EngagementSentimentCorrelation',
                    'Value': eng_insight.correlation_coefficient,
                    'Unit': 'None',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                })
                
                # Controversial posts (high engagement + negative sentiment)
                controversial_count = len(eng_insight.high_engagement_negative_posts)
                metric_data.append({
                    'MetricName': 'ControversialPosts',
                    'Value': controversial_count,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'DemoPhase', 'Value': str(self.demo_phase)}
                    ]
                })
            
            # Geographic sentiment metrics
            if 'geographic_insights' in insights and insights['geographic_insights']:
                for geo_insight in insights['geographic_insights'][:20]:  # Top 20 locations
                    metric_data.append({
                        'MetricName': 'GeographicSentiment',
                        'Value': geo_insight.average_sentiment,
                        'Unit': 'None',
                        'Timestamp': timestamp,
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment},
                            {'Name': 'Country', 'Value': sanitize_dimension_value(geo_insight.country)},
                            {'Name': 'City', 'Value': sanitize_dimension_value(geo_insight.city)}
                        ]
                    })
            
            # Publish metrics in batches of 20 (CloudWatch limit)
            for i in range(0, len(metric_data), 20):
                batch = metric_data[i:i+20]
                self.metrics_client.put_metric_data(
                    Namespace='SentimentAnalysis/Insights',
                    MetricData=batch
                )
            
            print(f"Published {len(metric_data)} insight metrics to CloudWatch")
            
        except Exception as e:
            print(f"Error publishing insight metrics: {e}")
            # Don't raise - metrics publishing failure shouldn't fail the Lambda
