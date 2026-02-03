"""
Sentiment Analyzer using Amazon Bedrock Nova Micro model.

This module provides sentiment analysis capabilities by invoking Amazon Bedrock's
Nova Micro model to classify social media posts and extract sentiment scores.
"""

import json
import logging
import time
import random
from typing import List, Dict, Any, Optional
from datetime import datetime

from models import SentimentResult

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ExponentialBackoff:
    """
    Helper class for implementing exponential backoff retry logic.
    
    Provides exponentially increasing delays between retry attempts with
    optional jitter to prevent thundering herd problems.
    
    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay_ms: Initial delay in milliseconds
        max_delay_ms: Maximum delay cap in milliseconds
        jitter: Whether to add random jitter to delays
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: float = 100.0,
        max_delay_ms: float = 5000.0,
        jitter: bool = True
    ):
        """
        Initialize exponential backoff configuration.
        
        Args:
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay_ms: Initial delay in milliseconds (default: 100ms)
            max_delay_ms: Maximum delay cap in milliseconds (default: 5000ms)
            jitter: Whether to add random jitter (default: True)
        """
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given retry attempt.
        
        Uses exponential backoff: delay = base_delay * (2 ^ attempt)
        Optionally adds jitter: delay *= random(0.5, 1.5)
        
        Args:
            attempt: Current retry attempt number (0-indexed)
            
        Returns:
            Delay in seconds (converted from milliseconds)
        """
        # Calculate exponential delay: 100ms, 200ms, 400ms, 800ms, ...
        delay_ms = min(self.base_delay_ms * (2 ** attempt), self.max_delay_ms)
        
        # Add jitter if enabled (±50% randomization)
        if self.jitter:
            jitter_factor = random.uniform(0.5, 1.5)
            delay_ms *= jitter_factor
        
        # Convert to seconds
        return delay_ms / 1000.0
    
    def should_retry(self, attempt: int, exception: Exception) -> bool:
        """
        Determine if an operation should be retried based on the exception type.
        
        Retryable errors:
        - ThrottlingException: Rate limit exceeded
        - InternalServerException: Temporary service issue
        
        Non-retryable errors:
        - ValidationException: Invalid request format
        - AccessDeniedException: Permission issue
        - Other exceptions: Unknown errors
        
        Args:
            attempt: Current retry attempt number (0-indexed)
            exception: The exception that was raised
            
        Returns:
            True if the operation should be retried, False otherwise
        """
        # Check if we've exceeded max retries
        if attempt >= self.max_retries:
            return False
        
        # Get exception name
        exception_name = exception.__class__.__name__
        
        # Check for retryable Bedrock exceptions
        retryable_exceptions = {
            'ThrottlingException',
            'InternalServerException',
            'ServiceUnavailableException',
            'TooManyRequestsException'
        }
        
        # Check if this is a boto3 client error
        if hasattr(exception, 'response'):
            error_code = exception.response.get('Error', {}).get('Code', '')
            if error_code in retryable_exceptions:
                logger.info(
                    f"Retryable error detected: {error_code}. "
                    f"Attempt {attempt + 1}/{self.max_retries}"
                )
                return True
        
        # Check exception class name as fallback
        if exception_name in retryable_exceptions:
            logger.info(
                f"Retryable error detected: {exception_name}. "
                f"Attempt {attempt + 1}/{self.max_retries}"
            )
            return True
        
        # Non-retryable error
        logger.warning(
            f"Non-retryable error detected: {exception_name}. "
            "Will not retry."
        )
        return False


class SentimentAnalyzer:
    """
    Analyzes sentiment of social media posts using Amazon Bedrock Nova Micro.
    
    This class handles batched sentiment analysis by constructing structured prompts,
    invoking the Bedrock API, and parsing JSON responses into SentimentResult objects.
    Includes automatic retry logic with exponential backoff for transient failures.
    
    Attributes:
        bedrock_client: Boto3 Bedrock Runtime client
        model_id: Bedrock model identifier (default: amazon.nova-micro-v1:0)
        backoff: ExponentialBackoff instance for retry logic
    """
    
    def __init__(
        self, 
        bedrock_client, 
        model_id: str = "amazon.nova-micro-v1:0",
        max_retries: int = 3
    ):
        """
        Initialize the sentiment analyzer.
        
        Args:
            bedrock_client: Boto3 bedrock-runtime client instance
            model_id: Bedrock model ID to use for analysis
            max_retries: Maximum number of retry attempts for failed API calls
        """
        self.bedrock_client = bedrock_client
        self.model_id = model_id
        self.backoff = ExponentialBackoff(
            max_retries=max_retries,
            base_delay_ms=100.0,  # 100ms, 200ms, 400ms
            max_delay_ms=5000.0,
            jitter=True
        )
        logger.info(
            f"Initialized SentimentAnalyzer with model: {model_id}, "
            f"max_retries: {max_retries}"
        )
    
    def analyze_batch(self, posts: List[Any]) -> List[SentimentResult]:
        """
        Analyze sentiment for a batch of social media posts.
        
        This method constructs a structured prompt containing all posts in the batch,
        invokes the Bedrock Nova Micro model, and parses the JSON response into
        SentimentResult objects.
        
        Args:
            posts: List of SocialMediaPost objects to analyze
            
        Returns:
            List of SentimentResult objects with sentiment classifications and scores
            
        Raises:
            ValueError: If the response cannot be parsed or is invalid
            Exception: If Bedrock API call fails after retries
        """
        if not posts:
            logger.warning("Empty batch provided to analyze_batch")
            return []
        
        start_time = time.time()
        
        try:
            # Construct the prompt
            prompt = self._build_prompt(posts)
            
            # Invoke Bedrock API
            logger.info(f"Analyzing batch of {len(posts)} posts with Bedrock")
            response = self._invoke_bedrock(prompt)
            
            # Parse response
            sentiment_results = self._parse_response(response, posts)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Update duration for each result
            for result in sentiment_results:
                result.analysis_duration_ms = duration_ms / len(sentiment_results)
            
            logger.info(
                f"Successfully analyzed {len(sentiment_results)} posts in {duration_ms:.2f}ms"
            )
            
            return sentiment_results
            
        except Exception as e:
            logger.error(f"Failed to analyze batch: {e}", exc_info=True)
            raise
    
    def _build_prompt(self, posts: List[Any]) -> str:
        """
        Build a structured prompt for Bedrock sentiment analysis.
        
        The prompt instructs the model to analyze each post and return results
        in a specific JSON format with sentiment classification, score, and confidence.
        
        Args:
            posts: List of SocialMediaPost objects
            
        Returns:
            Formatted prompt string
        """
        # Build the posts section
        posts_text = []
        for i, post in enumerate(posts, 1):
            post_text = f"{i}. Post ID: {post.id}\n   Content: {post.content}"
            if post.hashtags:
                post_text += f"\n   Hashtags: {', '.join(post.hashtags)}"
            posts_text.append(post_text)
        
        posts_section = "\n\n".join(posts_text)
        
        # Construct the full prompt
        prompt = f"""Analyze the sentiment of these social media posts. For each post, provide:
1. Sentiment classification (positive, negative, or neutral)
2. Sentiment intensity score from -1.0 (very negative) to 1.0 (very positive)
3. Confidence level from 0.0 to 1.0

Posts:
{posts_section}

Return results as a JSON array with this exact format:
[
  {{
    "post_id": "...",
    "sentiment": "positive|negative|neutral",
    "score": <float between -1.0 and 1.0>,
    "confidence": <float between 0.0 and 1.0>
  }}
]

Important:
- Analyze each post independently
- Use "positive" for optimistic/favorable content
- Use "negative" for pessimistic/critical content
- Use "neutral" for factual/balanced content
- Score should reflect intensity: -1.0 (very negative) to 1.0 (very positive)
- Confidence should reflect certainty of classification

Return ONLY the JSON array, no additional text."""
        
        return prompt
    
    def _invoke_bedrock(self, prompt: str) -> Dict[str, Any]:
        """
        Invoke the Bedrock API with the constructed prompt.
        
        This method handles the low-level API call to Bedrock, including
        request formatting, response extraction, and automatic retries with
        exponential backoff for transient failures.
        
        Args:
            prompt: The formatted prompt string
            
        Returns:
            Parsed response from Bedrock
            
        Raises:
            Exception: If API call fails after all retry attempts
        """
        # Construct the request body for Nova Micro
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "temperature": 0.0,  # Deterministic results
                "maxTokens": 2000,   # Sufficient for batch responses
                "topP": 1.0
            }
        }
        
        # Retry loop with exponential backoff
        attempt = 0
        last_exception = None
        
        while attempt <= self.backoff.max_retries:
            try:
                # Invoke the model
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body),
                    contentType="application/json",
                    accept="application/json"
                )
                
                # Parse the response
                response_body = json.loads(response['body'].read())
                
                # Success - log if this was a retry
                if attempt > 0:
                    logger.info(
                        f"Bedrock API call succeeded on attempt {attempt + 1}"
                    )
                
                return response_body
                
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if self.backoff.should_retry(attempt, e):
                    # Calculate delay
                    delay = self.backoff.get_delay(attempt)
                    
                    logger.warning(
                        f"Bedrock API call failed (attempt {attempt + 1}): {e}. "
                        f"Retrying in {delay:.3f}s..."
                    )
                    
                    # Wait before retrying
                    time.sleep(delay)
                    attempt += 1
                else:
                    # Non-retryable error or max retries exceeded
                    logger.error(
                        f"Bedrock API call failed after {attempt + 1} attempts: {e}"
                    )
                    raise
        
        # If we get here, we've exhausted all retries
        logger.error(
            f"Bedrock API call failed after {self.backoff.max_retries + 1} attempts"
        )
        raise last_exception
    
    def _parse_response(
        self, 
        response: Dict[str, Any], 
        posts: List[Any]
    ) -> List[SentimentResult]:
        """
        Parse Bedrock response into SentimentResult objects.
        
        Extracts the JSON array from the model's response and converts each
        entry into a validated SentimentResult object.
        
        Args:
            response: Raw response from Bedrock API
            posts: Original posts (for validation)
            
        Returns:
            List of SentimentResult objects
            
        Raises:
            ValueError: If response format is invalid or cannot be parsed
        """
        try:
            # Extract the content from Nova Micro response format
            if 'output' not in response:
                raise ValueError("Response missing 'output' field")
            
            output = response['output']
            if 'message' not in output:
                raise ValueError("Response output missing 'message' field")
            
            message = output['message']
            if 'content' not in message or not message['content']:
                raise ValueError("Response message missing 'content' field")
            
            # Get the text content
            content = message['content'][0]
            if 'text' not in content:
                raise ValueError("Response content missing 'text' field")
            
            text = content['text'].strip()
            
            # Extract JSON array from the text
            # The model might include markdown code blocks, so we need to extract the JSON
            json_text = self._extract_json(text)
            
            # Parse the JSON array
            sentiment_data = json.loads(json_text)
            
            if not isinstance(sentiment_data, list):
                raise ValueError(f"Expected JSON array, got {type(sentiment_data)}")
            
            # Convert to SentimentResult objects
            results = []
            for item in sentiment_data:
                try:
                    result = SentimentResult(
                        post_id=item['post_id'],
                        sentiment=item['sentiment'],
                        sentiment_score=float(item['score']),
                        confidence=float(item['confidence']),
                        timestamp=datetime.utcnow()
                    )
                    results.append(result)
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse sentiment item: {item}. Error: {e}")
                    continue
            
            # Validate we got results for all posts
            if len(results) != len(posts):
                logger.warning(
                    f"Result count mismatch: expected {len(posts)}, got {len(results)}"
                )
            
            return results
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from response: {e}")
            raise ValueError(f"Invalid JSON in Bedrock response: {e}")
        except Exception as e:
            logger.error(f"Failed to parse Bedrock response: {e}")
            raise ValueError(f"Failed to parse response: {e}")
    
    def _extract_json(self, text: str) -> str:
        """
        Extract JSON array from text that might contain markdown or other formatting.
        
        Args:
            text: Raw text from model response
            
        Returns:
            Extracted JSON string
        """
        # Remove markdown code blocks if present
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                text = text[start:end].strip()
        
        # Find the JSON array boundaries
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No JSON array found in response text")
        
        return text[start_idx:end_idx + 1]
