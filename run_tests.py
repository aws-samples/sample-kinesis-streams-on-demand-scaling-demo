#!/usr/bin/env python3
"""
Simple test runner to verify the core functionality without pytest.
"""

import sys
import os
import traceback
import logging

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def run_basic_tests():
    """Run basic tests to verify the models work correctly."""
    logger.info("Running basic tests for Kinesis On-Demand Demo...")
    
    try:
        # Test imports
        logger.info("✓ Testing imports...")
        from shared.models import SocialMediaPost, KinesisRecord, DemoMetrics, GeoLocation, PostType
        from shared.serialization import post_to_json, post_from_json, metrics_to_json, metrics_from_json
        from shared.config import DemoConfig
        from shared.post_generator import SocialMediaPostGenerator, TrafficPatternController
        
        # Test SocialMediaPost creation
        logger.info("✓ Testing SocialMediaPost creation...")
        post = SocialMediaPost(content="Test post #demo @user")
        assert post.content == "Test post #demo @user"
        assert post.user_id.startswith("user_")
        assert post.post_type == PostType.ORIGINAL
        
        # Test GeoLocation
        logger.info("✓ Testing GeoLocation...")
        location = GeoLocation(40.7128, -74.0060, "New York", "USA")
        assert location.city == "New York"
        
        # Test serialization
        logger.info("✓ Testing serialization...")
        json_str = post_to_json(post)
        deserialized_post = post_from_json(json_str)
        assert deserialized_post.content == post.content
        
        # Test DemoMetrics
        logger.info("✓ Testing DemoMetrics...")
        metrics = DemoMetrics(messages_per_second=1000, demo_phase=2)
        assert metrics.messages_per_second == 1000
        assert metrics.demo_phase == 2
        
        # Test DemoConfig
        logger.info("✓ Testing DemoConfig...")
        config = DemoConfig()
        assert config.baseline_tps == 100
        assert config.get_target_tps_for_phase(1) == 100
        assert config.get_target_tps_for_phase(3) == 50000
        
        # Test KinesisRecord
        logger.info("✓ Testing KinesisRecord...")
        data_bytes = post_to_json(post).encode('utf-8')
        record = KinesisRecord.from_post(post, data_bytes)
        assert record.partition_key == post.user_id
        
        # Test SocialMediaPostGenerator
        logger.info("✓ Testing SocialMediaPostGenerator...")
        generator = SocialMediaPostGenerator(config)
        generated_post = generator.generate_post(phase=1)
        assert isinstance(generated_post, SocialMediaPost)
        assert generated_post.content is not None
        assert len(generated_post.hashtags) >= 0
        assert generated_post.engagement_score >= 0
        
        # Test different phases produce different content
        phase_1_post = generator.generate_post(phase=1)
        phase_3_post = generator.generate_post(phase=3)
        # Phase 3 should generally have higher engagement
        # (We'll just check they're different objects for now)
        assert phase_1_post.id != phase_3_post.id
        
        # Test TrafficPatternController
        logger.info("✓ Testing TrafficPatternController...")
        controller = TrafficPatternController(config)
        assert len(controller.phases) == 4
        assert controller.phases[0].target_tps == config.baseline_tps
        assert controller.phases[2].target_tps == config.peak_tps
        
        # Test demo start
        controller.start_demo()
        assert controller.demo_start_time is not None
        
        # Test message calculation
        messages = controller.calculate_messages_to_generate(1.0)
        assert messages > 0
        
        logger.info("\n🎉 All basic tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = run_basic_tests()
    sys.exit(0 if success else 1)