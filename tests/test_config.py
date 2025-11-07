"""
Unit tests for configuration management.
"""

import pytest
import sys
import os

# Add the parent directory to the path so we can import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.config import DemoConfig


class TestDemoConfig:
    """Test DemoConfig class."""
    
    def test_default_values(self):
        """Test configuration with default values."""
        config = DemoConfig()
        
        assert config.baseline_tps == 100
        assert config.spike_tps == 10000
        assert config.peak_tps == 50000
        assert config.phase_durations == [120, 120, 120, 120]
        assert config.per_task_capacity == 1000
        assert config.max_tasks == 100
        assert config.stream_name == "social-media-stream"
        assert config.aws_region == "us-east-1"
    
    def test_custom_values(self):
        """Test configuration with custom values."""
        config = DemoConfig(
            baseline_tps=200,
            spike_tps=20000,
            peak_tps=100000,
            phase_durations=[60, 60, 60, 60],
            stream_name="custom-stream"
        )
        
        assert config.baseline_tps == 200
        assert config.spike_tps == 20000
        assert config.peak_tps == 100000
        assert config.phase_durations == [60, 60, 60, 60]
        assert config.stream_name == "custom-stream"
    
    def test_invalid_phase_durations(self):
        """Test validation of phase durations."""
        with pytest.raises(ValueError, match="Must have exactly 4 phase durations"):
            DemoConfig(phase_durations=[120, 120, 120])
        
        with pytest.raises(ValueError, match="All phase durations must be positive"):
            DemoConfig(phase_durations=[120, -60, 120, 120])
    
    def test_get_target_tps_for_phase(self):
        """Test getting target TPS for each phase."""
        config = DemoConfig()
        
        assert config.get_target_tps_for_phase(1) == 100
        assert config.get_target_tps_for_phase(2) == 10000
        assert config.get_target_tps_for_phase(3) == 50000
        assert config.get_target_tps_for_phase(4) == 100
        
        with pytest.raises(ValueError, match="Phase must be between 1 and 4"):
            config.get_target_tps_for_phase(5)
    
    def test_get_phase_duration(self):
        """Test getting phase duration."""
        config = DemoConfig(phase_durations=[60, 90, 120, 150])
        
        assert config.get_phase_duration(1) == 60
        assert config.get_phase_duration(2) == 90
        assert config.get_phase_duration(3) == 120
        assert config.get_phase_duration(4) == 150
    
    def test_get_total_demo_duration(self):
        """Test getting total demo duration."""
        config = DemoConfig(phase_durations=[60, 90, 120, 150])
        assert config.get_total_demo_duration() == 420