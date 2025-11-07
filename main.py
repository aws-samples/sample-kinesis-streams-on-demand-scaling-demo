#!/usr/bin/env python3
"""
Main containerized data generator application for Kinesis On-Demand Demo.

This application orchestrates social media post generation and Kinesis publishing
with phase-based traffic control and comprehensive monitoring.
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

from shared.config import DemoConfig
from shared.post_generator import SocialMediaPostGenerator, TrafficPatternController
from shared.kinesis_producer import KinesisProducer
from shared.models import PostType


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DemoDataGenerator:
    """
    Main data generator application that orchestrates the entire demo flow.
    
    Manages:
    - Demo phase transitions and timing
    - Traffic pattern control
    - Post generation and publishing
    - Metrics collection and reporting
    - Graceful shutdown handling
    """
    
    def __init__(self, config: DemoConfig):
        """Initialize the demo data generator."""
        self.config = config
        self.is_running = False
        self.shutdown_requested = False
        
        # Initialize components
        self.post_generator = SocialMediaPostGenerator(config)
        
        # Choose traffic controller based on configuration
        import os
        controller_mode = os.getenv('CONTROLLER_MODE', 'internal').lower()
        
        if controller_mode == 'step_functions':
            from shared.env_phase_controller import EnvironmentTrafficPatternController
            self.traffic_controller = EnvironmentTrafficPatternController(config)
            logger.info("Using Step Functions controller with environment variables for phase management")
        elif controller_mode == 'step_functions_polling':
            # Legacy polling mode - kept for backward compatibility
            from shared.stepfunctions_phase_controller import StepFunctionsTrafficPatternController
            service_name = os.getenv('SERVICE_NAME', 'kinesis-ondemand-demo-service')
            self.traffic_controller = StepFunctionsTrafficPatternController(config, service_name)
            logger.info("Using Step Functions controller with CloudWatch polling for phase management")

        else:
            from shared.post_generator import TrafficPatternController
            self.traffic_controller = TrafficPatternController(config)
            logger.info("Using internal phase management")
        
        self.kinesis_producer: Optional[KinesisProducer] = None
        
        # Demo state tracking
        self.demo_start_time: Optional[datetime] = None
        self.current_phase = 1
        self.total_messages_sent = 0
        self.total_messages_failed = 0
        
        # Performance tracking
        self.last_metrics_log = time.time()
        self.metrics_log_interval = 30  # Log metrics every 30 seconds
        
        # TPS tracking for metrics only
        self.tps_window_start = time.time()
        self.tps_window_messages = 0
        
        # Sliding window for accurate TPS calculation (last 30 seconds)
        self.tps_sliding_window = []  # List of (timestamp, message_count) tuples
        self.tps_window_duration = 30.0  # 30-second sliding window
        
        logger.info(f"DemoDataGenerator initialized with config: {config}")
    
    async def start(self) -> None:
        """Start the demo data generation process."""
        if self.is_running:
            logger.warning("Demo is already running")
            return
        
        logger.info("Starting Kinesis On-Demand Demo Data Generator")
        
        try:
            # Initialize Kinesis producer with environment-based configuration
            import os
            enable_cloudwatch = os.getenv('ENABLE_CLOUDWATCH_METRICS', 'true').lower() == 'true'
            metrics_interval = int(os.getenv('METRICS_PUBLISH_INTERVAL', '10'))
            
            self.kinesis_producer = KinesisProducer(
                config=self.config,
                max_batch_size=500,  # Kinesis PutRecords API limit
                max_batch_wait_ms=25,  # Reduced timeout for higher throughput
                enable_metrics=True,
                enable_cloudwatch_publishing=enable_cloudwatch,
                metrics_publish_interval=metrics_interval
            )
            
            # Start the demo
            self.is_running = True
            self.demo_start_time = datetime.utcnow()
            self.traffic_controller.start_demo()
            
            logger.info(f"Demo started at {self.demo_start_time}")
            logger.info(f"Total demo duration: {self.config.get_total_demo_duration()} seconds")
            
            # Start producer with metrics publishing
            async with self.kinesis_producer:
                await self._run_demo_loop()
                
        except Exception as e:
            logger.error(f"Error during demo execution: {e}")
            raise
        finally:
            self.is_running = False
            logger.info("Demo data generator stopped")
    
    async def _run_demo_loop(self) -> None:
        """Main demo loop that generates and publishes posts."""
        logger.info("Starting main demo loop")
        
        while self.is_running and not self.shutdown_requested:
            try:
                # Check if demo is complete
                if self.traffic_controller.is_demo_complete():
                    logger.info("Demo completed successfully")
                    break
                
                # Get current phase and update producer
                current_phase = self.traffic_controller.get_current_phase()
                if current_phase.phase_number != self.current_phase:
                    self.current_phase = current_phase.phase_number
                    self.kinesis_producer.set_demo_phase(self.current_phase)
                    logger.info(f"Transitioned to demo phase {self.current_phase}")
                    logger.info(f"Target TPS: {current_phase.target_tps}")
                    logger.info(f"Phase duration: {current_phase.duration_seconds}s")
                    logger.info(f"Remaining time in phase: {self.traffic_controller.get_remaining_time()}s")
                
                # Generate and send posts at maximum compute capacity
                await self._generate_and_send_posts()
                
                # Log metrics periodically
                await self._log_metrics_if_needed()
                
                # No artificial delays - run at maximum compute capacity
                
            except asyncio.CancelledError:
                logger.info("Demo loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in demo loop: {e}")
                # Continue running unless it's a critical error
                await asyncio.sleep(1)
    
    async def _generate_and_send_posts(self) -> None:
        """Generate and send posts at maximum compute capacity - no rate limiting."""
        target_tps = self.traffic_controller.get_target_tps()
        
        if target_tps == 0:
            return
        
        # Get post type distribution for current phase
        original_pct, share_pct, reply_pct = self.traffic_controller.get_post_type_distribution()
        
        # Generate posts in maximum batches for highest throughput
        batch_size = 500  # Always use maximum Kinesis batch size
        messages_to_send = batch_size
        
        # Generate batch of posts
        batch_posts = []
        for _ in range(messages_to_send):
            # Determine post type based on distribution
            rand_val = time.time() % 1.0  # Use time-based randomness
            if rand_val < original_pct:
                post_type = PostType.ORIGINAL
            elif rand_val < original_pct + share_pct:
                post_type = PostType.SHARE
            else:
                post_type = PostType.REPLY
            
            # Generate post
            post = self.post_generator.generate_post(
                phase=self.current_phase,
                post_type=post_type
            )
            batch_posts.append(post)
        
        # Send batch to Kinesis
        successful, failed = await self.kinesis_producer.send_posts_batch(batch_posts)
        
        # Update counters
        self.total_messages_sent += successful
        self.total_messages_failed += failed
        
        # Update TPS tracking window
        self.tps_window_messages += successful
        
        # Add to sliding window for accurate TPS calculation
        current_time = time.time()
        self.tps_sliding_window.append((current_time, successful))
        
        # Log throughput info periodically for monitoring
        if self.total_messages_sent % (batch_size * 20) == 0:  # Every 20 batches
            tps_metrics = self._get_tps_metrics()
            logger.debug(f"Max throughput mode: "
                       f"current_tps={tps_metrics['current_tps']:.1f}, "
                       f"recent_tps={tps_metrics['recent_tps']:.1f}, "
                       f"efficiency={tps_metrics['efficiency_percent']:.1f}%")
    
    def _get_current_tps(self) -> float:
        """Calculate current TPS based on sliding window of recent performance."""
        current_time = time.time()
        
        # Clean up old entries outside the sliding window
        cutoff_time = current_time - self.tps_window_duration
        self.tps_sliding_window = [
            (timestamp, count) for timestamp, count in self.tps_sliding_window
            if timestamp >= cutoff_time
        ]
        
        # Calculate TPS from sliding window
        if not self.tps_sliding_window:
            return 0.0
        
        # Sum messages in the sliding window
        total_messages = sum(count for _, count in self.tps_sliding_window)
        
        # Calculate actual time span of the window
        if len(self.tps_sliding_window) == 1:
            # Only one data point, use a minimum 1-second window
            window_duration = 1.0
        else:
            oldest_timestamp = self.tps_sliding_window[0][0]
            window_duration = max(current_time - oldest_timestamp, 1.0)
        
        return total_messages / window_duration
    
    def _get_tps_metrics(self) -> dict:
        """Get detailed TPS metrics for monitoring and CloudWatch."""
        current_time = time.time()
        
        # Get current TPS from sliding window
        current_tps = self._get_current_tps()
        
        # Calculate overall average TPS
        overall_tps = 0.0
        if self.demo_start_time:
            # Handle both datetime and float timestamp formats
            if hasattr(self.demo_start_time, 'timestamp'):
                start_timestamp = self.demo_start_time.timestamp()
            else:
                start_timestamp = self.demo_start_time
            
            total_duration = current_time - start_timestamp
            overall_tps = self.total_messages_sent / max(total_duration, 1)
        
        # Get target TPS
        target_tps = self.traffic_controller.get_target_tps()
        
        # Calculate efficiency
        efficiency = (current_tps / target_tps * 100) if target_tps > 0 else 0
        
        # Calculate recent performance (last 5 seconds for immediate feedback)
        recent_cutoff = current_time - 5.0
        recent_messages = sum(
            count for timestamp, count in self.tps_sliding_window
            if timestamp >= recent_cutoff
        )
        recent_tps = recent_messages / 5.0 if recent_messages > 0 else 0.0
        
        return {
            'current_tps': current_tps,
            'recent_tps': recent_tps,
            'overall_tps': overall_tps,
            'target_tps': target_tps,
            'efficiency_percent': efficiency,
            'total_messages': self.total_messages_sent,
            'sliding_window_size': len(self.tps_sliding_window)
        }
    
    async def _log_metrics_if_needed(self) -> None:
        """Log metrics periodically for monitoring."""
        current_time = time.time()
        if current_time - self.last_metrics_log >= self.metrics_log_interval:
            await self._log_current_metrics()
            self.last_metrics_log = current_time
    
    async def _log_current_metrics(self) -> None:
        """Log current demo metrics."""
        if not self.kinesis_producer:
            return
        
        # Get producer metrics
        producer_metrics = self.kinesis_producer.get_metrics()
        
        # Get demo progress
        demo_progress = self.traffic_controller.get_demo_progress()
        phase_progress = self.traffic_controller.get_phase_progress()
        remaining_time = self.traffic_controller.get_remaining_time()
        target_tps = self.traffic_controller.get_target_tps()
        
        # Get detailed TPS performance metrics
        tps_metrics = self._get_tps_metrics()
        
        # Log comprehensive metrics
        logger.info("=== DEMO METRICS ===")
        logger.info(f"Demo Phase: {self.current_phase}/4")
        logger.info(f"Demo Progress: {demo_progress:.1%}")
        logger.info(f"Phase Progress: {phase_progress:.1%}")
        logger.info(f"Remaining Time in Phase: {remaining_time}s")
        logger.info(f"Target TPS: {tps_metrics['target_tps']}")
        logger.info(f"Current TPS (30s avg): {tps_metrics['current_tps']:.1f} ({tps_metrics['efficiency_percent']:.1f}% of target)")
        logger.info(f"Recent TPS (5s avg): {tps_metrics['recent_tps']:.1f}")
        logger.info(f"Overall TPS: {tps_metrics['overall_tps']:.1f}")
        logger.info(f"Total Messages Sent: {self.total_messages_sent}")
        logger.info(f"Total Messages Failed: {self.total_messages_failed}")
        logger.info(f"Producer Success Rate: {producer_metrics.get_success_rate():.1f}%")
        logger.info(f"Producer Avg Latency: {producer_metrics.get_average_latency_ms():.1f}ms")
        logger.info(f"Producer Avg Message Size: {producer_metrics.get_average_message_size():.1f} bytes")
        logger.info(f"Producer Throttle Count: {producer_metrics.throttle_exceptions}")
        logger.info(f"Producer Batch Count: {producer_metrics.batch_count}")
        logger.info(f"TPS Window Size: {tps_metrics['sliding_window_size']} data points")
        logger.info("==================")
    
    async def stop(self) -> None:
        """Stop the demo gracefully."""
        logger.info("Stopping demo data generator...")
        self.shutdown_requested = True
        
        # Wait a moment for current operations to complete
        await asyncio.sleep(1)
        
        # Final metrics log
        if self.is_running:
            await self._log_current_metrics()
        
        self.is_running = False
        logger.info("Demo data generator stopped")
    
    def get_demo_status(self) -> dict:
        """Get current demo status for health checks."""
        if not self.is_running:
            return {
                'status': 'stopped',
                'demo_progress': 0.0,
                'current_phase': 0,
                'total_messages_sent': self.total_messages_sent,
                'total_messages_failed': self.total_messages_failed
            }
        
        return {
            'status': 'running',
            'demo_progress': self.traffic_controller.get_demo_progress(),
            'phase_progress': self.traffic_controller.get_phase_progress(),
            'current_phase': self.current_phase,
            'target_tps': self.traffic_controller.get_target_tps(),
            'remaining_time': self.traffic_controller.get_remaining_time(),
            'total_messages_sent': self.total_messages_sent,
            'total_messages_failed': self.total_messages_failed,
            'demo_start_time': self.demo_start_time.isoformat() if self.demo_start_time else None
        }


class SignalHandler:
    """Handles graceful shutdown on SIGTERM/SIGINT."""
    
    def __init__(self, demo_generator: DemoDataGenerator):
        self.demo_generator = demo_generator
        self.shutdown_event = asyncio.Event()
    
    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        if sys.platform != 'win32':
            # Unix-like systems
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._signal_handler)
        else:
            # Windows
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum=None, frame=None) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received shutdown signal {signum}")
        self.shutdown_event.set()
    
    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self.shutdown_event.wait()


async def main() -> None:
    """Main entry point for the containerized application."""
    logger.info("Starting Kinesis On-Demand Demo Data Generator")
    
    try:
        # Load configuration from environment
        config = DemoConfig.from_environment()
        logger.info(f"Loaded configuration: {config}")
        
        # Create demo generator
        demo_generator = DemoDataGenerator(config)
        
        # Set up signal handling for graceful shutdown
        signal_handler = SignalHandler(demo_generator)
        signal_handler.setup_signal_handlers()
        
        # Start demo in background task
        demo_task = asyncio.create_task(demo_generator.start())
        
        # Wait for either demo completion or shutdown signal
        shutdown_task = asyncio.create_task(signal_handler.wait_for_shutdown())
        
        try:
            # Wait for either demo completion or shutdown
            done, pending = await asyncio.wait(
                [demo_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # If shutdown was requested, stop the demo
            if shutdown_task in done:
                logger.info("Shutdown requested, stopping demo...")
                await demo_generator.stop()
            
            # Wait for demo task to complete if it hasn't already
            if demo_task not in done:
                try:
                    await demo_task
                except asyncio.CancelledError:
                    pass
        
        except Exception as e:
            logger.error(f"Error during demo execution: {e}")
            await demo_generator.stop()
            raise
        
        logger.info("Demo completed successfully")
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Run the main application
    asyncio.run(main())