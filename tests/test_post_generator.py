"""
Unit tests for social media post generation logic.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from shared.post_generator import SocialMediaPostGenerator, TrafficPatternController, TrafficPhase
from shared.models import SocialMediaPost, PostType, GeoLocation
from shared.config import DemoConfig


class TestSocialMediaPostGenerator:
    """Test cases for SocialMediaPostGenerator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = DemoConfig()
        self.generator = SocialMediaPostGenerator(self.config)
    
    def test_generate_post_basic(self):
        """Test basic post generation."""
        post = self.generator.generate_post()
        
        assert isinstance(post, SocialMediaPost)
        assert post.id is not None
        assert post.user_id is not None
        assert post.username is not None
        assert post.content is not None
        assert isinstance(post.hashtags, list)
        assert isinstance(post.mentions, list)
        assert isinstance(post.engagement_score, float)
        assert post.engagement_score >= 0
        assert isinstance(post.timestamp, datetime)
    
    def test_generate_post_phase_1_baseline(self):
        """Test post generation for phase 1 (baseline)."""
        post = self.generator.generate_post(phase=1)
        
        # Phase 1 should have fewer hashtags and lower engagement
        assert len(post.hashtags) <= 2
        assert post.engagement_score <= 2.0
        assert post.post_type == PostType.ORIGINAL
    
    def test_generate_post_phase_2_spike(self):
        """Test post generation for phase 2 (spike/breaking news)."""
        post = self.generator.generate_post(phase=2)
        
        # Phase 2 should have more hashtags and higher engagement
        assert len(post.hashtags) >= 2
        assert len(post.hashtags) <= 4
        assert post.engagement_score >= 2.0
        # Content should contain breaking news elements
        assert any(keyword in post.content.lower() for keyword in ['breaking', 'urgent', 'just in', 'alert'])
    
    def test_generate_post_phase_3_peak(self):
        """Test post generation for phase 3 (peak viral)."""
        post = self.generator.generate_post(phase=3)
        
        # Phase 3 should have most hashtags and highest engagement
        assert len(post.hashtags) >= 3
        assert len(post.hashtags) <= 6
        assert post.engagement_score >= 8.0
        # Content should be viral-style
        assert any(keyword in post.content.lower() for keyword in ['incredible', 'amazing', 'everyone', 'mind'])
    
    def test_generate_post_phase_4_decline(self):
        """Test post generation for phase 4 (decline)."""
        post = self.generator.generate_post(phase=4)
        
        # Phase 4 should be similar to phase 1 but with some viral remnants
        assert len(post.hashtags) <= 3
        assert 1.0 <= post.engagement_score <= 5.0
    
    def test_generate_post_different_types(self):
        """Test generation of different post types."""
        original_post = self.generator.generate_post(post_type=PostType.ORIGINAL)
        share_post = self.generator.generate_post(post_type=PostType.SHARE)
        reply_post = self.generator.generate_post(post_type=PostType.REPLY)
        
        assert original_post.post_type == PostType.ORIGINAL
        assert share_post.post_type == PostType.SHARE
        assert reply_post.post_type == PostType.REPLY
        
        # Share posts should have RT prefix
        assert share_post.content.startswith("RT:")
        # Reply posts should have @ mention
        assert reply_post.content.startswith("@")
    
    def test_generate_hashtags_phase_variation(self):
        """Test hashtag generation varies by phase."""
        # Generate multiple posts for each phase to test variation
        phase_1_hashtags = []
        phase_3_hashtags = []
        
        for _ in range(10):
            phase_1_hashtags.extend(self.generator._generate_hashtags(1))
            phase_3_hashtags.extend(self.generator._generate_hashtags(3))
        
        # Phase 3 should generally have more hashtags
        avg_phase_1 = len(phase_1_hashtags) / 10
        avg_phase_3 = len(phase_3_hashtags) / 10
        assert avg_phase_3 > avg_phase_1
    
    def test_generate_mentions_phase_variation(self):
        """Test mention generation varies by phase."""
        phase_1_mentions = []
        phase_3_mentions = []
        
        for _ in range(20):
            phase_1_mentions.extend(self.generator._generate_mentions(1))
            phase_3_mentions.extend(self.generator._generate_mentions(3))
        
        # Phase 3 should generally have more mentions
        assert len(phase_3_mentions) >= len(phase_1_mentions)
    
    def test_generate_location_optional(self):
        """Test that location generation is optional."""
        locations = []
        for _ in range(100):
            location = self.generator._generate_location()
            locations.append(location)
        
        # Should have some None values (about 30%)
        none_count = sum(1 for loc in locations if loc is None)
        assert 20 <= none_count <= 40  # Allow some variance
        
        # Non-None locations should be valid
        valid_locations = [loc for loc in locations if loc is not None]
        for location in valid_locations:
            assert isinstance(location, GeoLocation)
            assert -90 <= location.latitude <= 90
            assert -180 <= location.longitude <= 180
            assert location.city is not None
            assert location.country is not None
    
    def test_generate_engagement_score_phase_correlation(self):
        """Test engagement scores correlate with phases."""
        phase_1_scores = [self.generator._generate_engagement_score(1) for _ in range(50)]
        phase_3_scores = [self.generator._generate_engagement_score(3) for _ in range(50)]
        
        avg_phase_1 = sum(phase_1_scores) / len(phase_1_scores)
        avg_phase_3 = sum(phase_3_scores) / len(phase_3_scores)
        
        # Phase 3 should have significantly higher engagement
        assert avg_phase_3 > avg_phase_1 * 2
    
    def test_generate_username_variety(self):
        """Test username generation produces variety."""
        usernames = set()
        for _ in range(100):
            username = self.generator._generate_username()
            usernames.add(username)
            assert isinstance(username, str)
            assert len(username) > 0
        
        # Should generate many unique usernames
        assert len(usernames) > 80


class TestTrafficPatternController:
    """Test cases for TrafficPatternController class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = DemoConfig()
        self.controller = TrafficPatternController(self.config)
    
    def test_initialization(self):
        """Test controller initialization."""
        assert len(self.controller.phases) == 4
        assert self.controller.demo_start_time is None
        assert self.controller.current_phase_index == 0
        
        # Check phase configuration
        for i, phase in enumerate(self.controller.phases):
            assert phase.phase_number == i + 1
            assert phase.target_tps == self.config.get_target_tps_for_phase(i + 1)
            assert phase.duration_seconds == self.config.get_phase_duration(i + 1)
    
    def test_start_demo(self):
        """Test demo start functionality."""
        start_time = datetime.utcnow()
        self.controller.start_demo()
        
        assert self.controller.demo_start_time is not None
        assert self.controller.demo_start_time >= start_time
        
        # All phases should have start times set
        for phase in self.controller.phases:
            assert phase.start_time is not None
    
    def test_get_current_phase_before_start(self):
        """Test getting current phase before demo starts."""
        with pytest.raises(RuntimeError, match="Demo has not been started"):
            self.controller.get_current_phase()
    
    @patch('shared.post_generator.datetime')
    def test_get_current_phase_progression(self, mock_datetime):
        """Test phase progression over time."""
        # Mock the start time
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = start_time
        
        self.controller.start_demo()
        
        # Test phase 1 (0-120 seconds)
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=60)
        current_phase = self.controller.get_current_phase()
        assert current_phase.phase_number == 1
        
        # Test phase 2 (120-240 seconds)
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=180)
        current_phase = self.controller.get_current_phase()
        assert current_phase.phase_number == 2
        
        # Test phase 3 (240-360 seconds)
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=300)
        current_phase = self.controller.get_current_phase()
        assert current_phase.phase_number == 3
        
        # Test phase 4 (360-480 seconds)
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=420)
        current_phase = self.controller.get_current_phase()
        assert current_phase.phase_number == 4
        
        # Test after demo completion
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=600)
        current_phase = self.controller.get_current_phase()
        assert current_phase.phase_number == 4  # Should stay at last phase
    
    def test_get_target_tps(self):
        """Test target TPS calculation."""
        self.controller.start_demo()
        
        # Mock different phases and test TPS
        with patch.object(self.controller, 'get_current_phase') as mock_get_phase:
            # Test phase 1
            mock_get_phase.return_value = self.controller.phases[0]
            assert self.controller.get_target_tps() == self.config.baseline_tps
            
            # Test phase 2
            mock_get_phase.return_value = self.controller.phases[1]
            assert self.controller.get_target_tps() == self.config.spike_tps
            
            # Test phase 3
            mock_get_phase.return_value = self.controller.phases[2]
            assert self.controller.get_target_tps() == self.config.peak_tps
    
    @patch('shared.post_generator.datetime')
    def test_get_phase_progress(self, mock_datetime):
        """Test phase progress calculation."""
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = start_time
        
        self.controller.start_demo()
        
        # Test 50% through phase 1
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=60)
        progress = self.controller.get_phase_progress()
        assert abs(progress - 0.5) < 0.01
        
        # Test 100% through phase 1
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=120)
        progress = self.controller.get_phase_progress()
        assert abs(progress - 1.0) < 0.01
    
    @patch('shared.post_generator.datetime')
    def test_get_demo_progress(self, mock_datetime):
        """Test overall demo progress calculation."""
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = start_time
        
        self.controller.start_demo()
        
        # Test 25% through demo (2 minutes into 8-minute demo)
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=120)
        progress = self.controller.get_demo_progress()
        assert abs(progress - 0.25) < 0.01
        
        # Test 100% through demo
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=480)
        progress = self.controller.get_demo_progress()
        assert abs(progress - 1.0) < 0.01
    
    @patch('shared.post_generator.datetime')
    def test_is_demo_complete(self, mock_datetime):
        """Test demo completion detection."""
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = start_time
        
        self.controller.start_demo()
        
        # Demo should not be complete initially
        assert not self.controller.is_demo_complete()
        
        # Demo should be complete after total duration
        mock_datetime.utcnow.return_value = start_time + timedelta(seconds=480)
        assert self.controller.is_demo_complete()
    
    def test_calculate_messages_to_generate(self):
        """Test message calculation for time windows."""
        self.controller.start_demo()
        
        with patch.object(self.controller, 'get_target_tps', return_value=1000):
            # Test 1-second window
            messages = self.controller.calculate_messages_to_generate(1.0)
            assert messages == 1000
            
            # Test 0.5-second window
            messages = self.controller.calculate_messages_to_generate(0.5)
            assert messages == 500
            
            # Test 2-second window
            messages = self.controller.calculate_messages_to_generate(2.0)
            assert messages == 2000
    
    def test_get_post_type_distribution(self):
        """Test post type distribution varies by phase."""
        self.controller.start_demo()
        
        # Test early phase distribution
        with patch.object(self.controller, 'get_current_phase') as mock_get_phase:
            mock_get_phase.return_value = self.controller.phases[0]  # Phase 1
            original, share, reply = self.controller.get_post_type_distribution()
            assert original == 0.7
            assert share == 0.2
            assert reply == 0.1
            
            # Test viral phase distribution
            mock_get_phase.return_value = self.controller.phases[2]  # Phase 3
            original, share, reply = self.controller.get_post_type_distribution()
            assert original == 0.4
            assert share == 0.4
            assert reply == 0.2


class TestTrafficPhase:
    """Test cases for TrafficPhase class."""
    
    def test_traffic_phase_creation(self):
        """Test TrafficPhase creation."""
        phase = TrafficPhase(
            phase_number=1,
            target_tps=100,
            duration_seconds=120
        )
        
        assert phase.phase_number == 1
        assert phase.target_tps == 100
        assert phase.duration_seconds == 120
        assert phase.start_time is None
        assert phase.end_time is None
    
    def test_end_time_calculation(self):
        """Test end time calculation."""
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        phase = TrafficPhase(
            phase_number=1,
            target_tps=100,
            duration_seconds=120,
            start_time=start_time
        )
        
        expected_end_time = start_time + timedelta(seconds=120)
        assert phase.end_time == expected_end_time


class TestIntegration:
    """Integration tests for post generation and traffic control."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = DemoConfig()
        self.generator = SocialMediaPostGenerator(self.config)
        self.controller = TrafficPatternController(self.config)
    
    def test_full_demo_simulation(self):
        """Test a complete demo simulation."""
        self.controller.start_demo()
        
        # Simulate generating posts for each phase
        posts_by_phase = {1: [], 2: [], 3: [], 4: []}
        
        with patch.object(self.controller, 'get_current_phase') as mock_get_phase:
            for phase_num in range(1, 5):
                mock_get_phase.return_value = self.controller.phases[phase_num - 1]
                
                # Generate some posts for this phase
                for _ in range(10):
                    post = self.generator.generate_post(phase=phase_num)
                    posts_by_phase[phase_num].append(post)
        
        # Verify posts were generated for all phases
        for phase_num in range(1, 5):
            assert len(posts_by_phase[phase_num]) == 10
            
        # Verify phase 3 has higher engagement on average
        phase_1_engagement = sum(p.engagement_score for p in posts_by_phase[1]) / 10
        phase_3_engagement = sum(p.engagement_score for p in posts_by_phase[3]) / 10
        assert phase_3_engagement > phase_1_engagement
    
    def test_realistic_traffic_generation(self):
        """Test realistic traffic generation patterns."""
        self.controller.start_demo()
        
        # Test message generation for different phases
        with patch.object(self.controller, 'get_target_tps') as mock_get_tps:
            # Phase 1: baseline
            mock_get_tps.return_value = 100
            messages_1s = self.controller.calculate_messages_to_generate(1.0)
            assert messages_1s == 100
            
            # Phase 3: peak
            mock_get_tps.return_value = 50000
            messages_1s = self.controller.calculate_messages_to_generate(1.0)
            assert messages_1s == 50000
            
            # Fractional second
            messages_100ms = self.controller.calculate_messages_to_generate(0.1)
            assert messages_100ms == 5000