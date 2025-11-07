"""
Configuration management for demo parameters.
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class DemoConfig:
    """Configuration parameters for the Kinesis On-Demand Demo."""
    
    # Phase durations in seconds (kept for backward compatibility)
    phase_durations: List[int] = None
    
    # Kinesis configuration
    stream_name: str = "social-media-stream"
    
    # AWS configuration
    aws_region: str = "us-east-1"
    
    # Cost calculation
    kinesis_shard_hour_cost: float = 0.015
    kinesis_payload_unit_cost: float = 0.000014
    lambda_gb_second_cost: float = 0.0000166667
    lambda_request_cost: float = 0.0000002
    ecs_vcpu_hour_cost: float = 0.04048
    ecs_gb_hour_cost: float = 0.004445
    
    def __post_init__(self):
        """Initialize default values and validate configuration."""
        if self.phase_durations is None:
            self.phase_durations = [120, 120, 120, 120]  # 2 minutes each phase
        
        # Validate phase durations
        if len(self.phase_durations) != 4:
            raise ValueError("Must have exactly 4 phase durations")
        
        if any(duration <= 0 for duration in self.phase_durations):
            raise ValueError("All phase durations must be positive")
    
    @classmethod
    def from_environment(cls) -> 'DemoConfig':
        """Create configuration from environment variables."""
        return cls(
            stream_name=os.getenv('STREAM_NAME', 'social-media-stream'),
            aws_region=os.getenv('AWS_REGION', 'us-east-1')
        )
    

    
    def get_phase_duration(self, phase: int) -> int:
        """Get duration in seconds for a given demo phase (1-4)."""
        if not 1 <= phase <= 4:
            raise ValueError("Phase must be between 1 and 4")
        return self.phase_durations[phase - 1]
    
    def get_total_demo_duration(self) -> int:
        """Get total demo duration in seconds."""
        return sum(self.phase_durations)