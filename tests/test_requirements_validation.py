#!/usr/bin/env python3
"""
Validation tests to ensure post generation meets specific requirements.
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from unittest.mock import patch

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.post_generator import SocialMediaPostGenerator, TrafficPatternController
from shared.models import SocialMediaPost, PostType
from shared.config import DemoConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def test_requirement_1_1_baseline_traffic():
    """Test Requirement 1.1: System generates 100 posts per second as baseline traffic."""
    logger.info("Testing Requirement 1.1: Baseline traffic generation...")
    
    config = DemoConfig()
    controller = TrafficPatternController(config)
    controller.start_demo()
    
    # Mock to be in phase 1
    with patch.object(controller, 'get_current_phase') as mock_get_phase:
        mock_get_phase.return_value = controller.phases[0]  # Phase 1
        
        target_tps = controller.get_target_tps()
        messages_per_second = controller.calculate_messages_to_generate(1.0)
        
        assert target_tps == 100, f"Expected 100 TPS, got {target_tps}"
        assert messages_per_second == 100, f"Expected 100 messages/sec, got {messages_per_second}"
    
    logger.info("✓ Requirement 1.1 validated")


def test_requirement_1_2_viral_event_traffic():
    """Test Requirement 1.2: System increases traffic to 10,000+ posts per second during viral event."""
    logger.info("Testing Requirement 1.2: Viral event traffic increase...")
    
    config = DemoConfig()
    controller = TrafficPatternController(config)
    controller.start_demo()
    
    # Mock to be in phase 2 (spike phase)
    with patch.object(controller, 'get_current_phase') as mock_get_phase:
        mock_get_phase.return_value = controller.phases[1]  # Phase 2
        
        target_tps = controller.get_target_tps()
        messages_per_second = controller.calculate_messages_to_generate(1.0)
        
        assert target_tps >= 10000, f"Expected ≥10,000 TPS, got {target_tps}"
        assert messages_per_second >= 10000, f"Expected ≥10,000 messages/sec, got {messages_per_second}"
    
    logger.info("✓ Requirement 1.2 validated")


def test_requirement_1_3_peak_viral_traffic():
    """Test Requirement 1.3: System surges traffic to 50,000+ posts per second during peak viral moment."""
    logger.info("Testing Requirement 1.3: Peak viral traffic surge...")
    
    config = DemoConfig()
    controller = TrafficPatternController(config)
    controller.start_demo()
    
    # Mock to be in phase 3 (peak phase)
    with patch.object(controller, 'get_current_phase') as mock_get_phase:
        mock_get_phase.return_value = controller.phases[2]  # Phase 3
        
        target_tps = controller.get_target_tps()
        messages_per_second = controller.calculate_messages_to_generate(1.0)
        
        assert target_tps >= 50000, f"Expected ≥50,000 TPS, got {target_tps}"
        assert messages_per_second >= 50000, f"Expected ≥50,000 messages/sec, got {messages_per_second}"
    
    logger.info("✓ Requirement 1.3 validated")


def test_requirement_1_4_traffic_decline():
    """Test Requirement 1.4: System gradually decreases traffic back to baseline during decline."""
    logger.info("Testing Requirement 1.4: Traffic decline to baseline...")
    
    config = DemoConfig()
    controller = TrafficPatternController(config)
    controller.start_demo()
    
    # Mock to be in phase 4 (decline phase)
    with patch.object(controller, 'get_current_phase') as mock_get_phase:
        mock_get_phase.return_value = controller.phases[3]  # Phase 4
        
        target_tps = controller.get_target_tps()
        messages_per_second = controller.calculate_messages_to_generate(1.0)
        
        # Phase 4 should return to baseline (100 TPS)
        assert target_tps == 100, f"Expected 100 TPS in decline phase, got {target_tps}"
        assert messages_per_second == 100, f"Expected 100 messages/sec in decline phase, got {messages_per_second}"
    
    logger.info("✓ Requirement 1.4 validated")


def test_requirement_1_5_realistic_social_media_elements():
    """Test Requirement 1.5: Posts include realistic social media elements (hashtags, mentions, geographic spread)."""
    logger.info("Testing Requirement 1.5: Realistic social media elements...")
    
    config = DemoConfig()
    generator = SocialMediaPostGenerator(config)
    
    # Generate multiple posts to test variety
    posts = []
    for phase in range(1, 5):
        for _ in range(20):
            post = generator.generate_post(phase=phase)
            posts.append(post)
    
    # Check hashtags
    posts_with_hashtags = [p for p in posts if len(p.hashtags) > 0]
    hashtag_ratio = len(posts_with_hashtags) / len(posts)
    assert hashtag_ratio > 0.8, f"Expected >80% posts with hashtags, got {hashtag_ratio:.2%}"
    
    # Check mentions (should be present in some posts, especially viral phases)
    posts_with_mentions = [p for p in posts if len(p.mentions) > 0]
    mention_ratio = len(posts_with_mentions) / len(posts)
    assert mention_ratio > 0.3, f"Expected >30% posts with mentions, got {mention_ratio:.2%}"
    
    # Check geographic spread (should be present in ~70% of posts)
    posts_with_location = [p for p in posts if p.location is not None]
    location_ratio = len(posts_with_location) / len(posts)
    assert 0.6 <= location_ratio <= 0.8, f"Expected 60-80% posts with location, got {location_ratio:.2%}"
    
    # Verify geographic data is realistic
    for post in posts_with_location[:10]:  # Check first 10
        assert -90 <= post.location.latitude <= 90, f"Invalid latitude: {post.location.latitude}"
        assert -180 <= post.location.longitude <= 180, f"Invalid longitude: {post.location.longitude}"
        assert post.location.city, "City should not be empty"
        assert post.location.country, "Country should not be empty"
    
    # Check content variety
    unique_content = set(p.content for p in posts)
    content_variety = len(unique_content) / len(posts)
    assert content_variety > 0.5, f"Expected >50% unique content, got {content_variety:.2%}"
    
    logger.info("✓ Requirement 1.5 validated")


def test_traffic_pattern_timing():
    """Test that traffic patterns follow the correct timing for demo phases."""
    logger.info("Testing traffic pattern timing...")
    
    config = DemoConfig()
    controller = TrafficPatternController(config)
    
    # Verify phase durations
    total_duration = controller.config.get_total_demo_duration()
    assert total_duration == 480, f"Expected 8-minute demo (480s), got {total_duration}s"
    
    # Verify each phase is 2 minutes (120 seconds)
    for i, phase in enumerate(controller.phases):
        expected_duration = 120
        assert phase.duration_seconds == expected_duration, \
            f"Phase {i+1} should be {expected_duration}s, got {phase.duration_seconds}s"
    
    logger.info("✓ Traffic pattern timing validated")


def test_phase_content_characteristics():
    """Test that content characteristics match phase requirements."""
    logger.info("Testing phase-specific content characteristics...")
    
    config = DemoConfig()
    generator = SocialMediaPostGenerator(config)
    
    # Test Phase 1 (baseline) characteristics
    phase_1_posts = [generator.generate_post(phase=1) for _ in range(50)]
    avg_engagement_1 = sum(p.engagement_score for p in phase_1_posts) / len(phase_1_posts)
    avg_hashtags_1 = sum(len(p.hashtags) for p in phase_1_posts) / len(phase_1_posts)
    
    # Test Phase 3 (peak viral) characteristics
    phase_3_posts = [generator.generate_post(phase=3) for _ in range(50)]
    avg_engagement_3 = sum(p.engagement_score for p in phase_3_posts) / len(phase_3_posts)
    avg_hashtags_3 = sum(len(p.hashtags) for p in phase_3_posts) / len(phase_3_posts)
    
    # Phase 3 should have significantly higher engagement and more hashtags
    assert avg_engagement_3 > avg_engagement_1 * 2, \
        f"Phase 3 engagement ({avg_engagement_3:.2f}) should be >2x Phase 1 ({avg_engagement_1:.2f})"
    
    assert avg_hashtags_3 > avg_hashtags_1, \
        f"Phase 3 hashtags ({avg_hashtags_3:.2f}) should be > Phase 1 ({avg_hashtags_1:.2f})"
    
    # Check for viral content keywords in phase 3
    viral_keywords = ['incredible', 'amazing', 'everyone', 'mind', 'unbelievable', 'wow']
    phase_3_viral_content = sum(1 for p in phase_3_posts 
                               if any(keyword in p.content.lower() for keyword in viral_keywords))
    viral_ratio = phase_3_viral_content / len(phase_3_posts)
    assert viral_ratio > 0.3, f"Expected >30% viral content in phase 3, got {viral_ratio:.2%}"
    
    logger.info("✓ Phase content characteristics validated")


def test_post_type_distribution():
    """Test that post type distribution varies appropriately by phase."""
    logger.info("Testing post type distribution by phase...")
    
    config = DemoConfig()
    controller = TrafficPatternController(config)
    controller.start_demo()
    
    # Test early phase distribution (should favor original content)
    with patch.object(controller, 'get_current_phase') as mock_get_phase:
        mock_get_phase.return_value = controller.phases[0]  # Phase 1
        original_1, share_1, reply_1 = controller.get_post_type_distribution()
        
        assert original_1 == 0.7, f"Phase 1 should have 70% original posts, got {original_1}"
        assert share_1 == 0.2, f"Phase 1 should have 20% shares, got {share_1}"
        assert reply_1 == 0.1, f"Phase 1 should have 10% replies, got {reply_1}"
        
        # Test viral phase distribution (should have more shares/replies)
        mock_get_phase.return_value = controller.phases[2]  # Phase 3
        original_3, share_3, reply_3 = controller.get_post_type_distribution()
        
        assert original_3 == 0.4, f"Phase 3 should have 40% original posts, got {original_3}"
        assert share_3 == 0.4, f"Phase 3 should have 40% shares, got {share_3}"
        assert reply_3 == 0.2, f"Phase 3 should have 20% replies, got {reply_3}"
    
    logger.info("✓ Post type distribution validated")


def run_all_requirement_tests():
    """Run all requirement validation tests."""
    logger.info("=" * 60)
    logger.info("RUNNING REQUIREMENT VALIDATION TESTS")
    logger.info("=" * 60)
    
    tests = [
        test_requirement_1_1_baseline_traffic,
        test_requirement_1_2_viral_event_traffic,
        test_requirement_1_3_peak_viral_traffic,
        test_requirement_1_4_traffic_decline,
        test_requirement_1_5_realistic_social_media_elements,
        test_traffic_pattern_timing,
        test_phase_content_characteristics,
        test_post_type_distribution,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            logger.error(f"❌ {test_func.__name__} FAILED: {e}")
            failed += 1
    
    logger.info("=" * 60)
    logger.info(f"RESULTS: {passed} passed, {failed} failed")
    logger.info("=" * 60)
    
    if failed == 0:
        logger.info("🎉 All requirement validation tests passed!")
        return True
    else:
        logger.error("❌ Some tests failed!")
        return False


if __name__ == "__main__":
    success = run_all_requirement_tests()
    sys.exit(0 if success else 1)