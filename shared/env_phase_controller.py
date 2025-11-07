"""
Environment Variable Phase Controller

This module allows containers to get their current phase and target TPS
from environment variables set during ECS task deployment, eliminating
the need for polling CloudWatch metrics or Parameter Store.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class EnvironmentPhaseController:
    """
    Client for getting phase information from environment variables.
    
    This replaces CloudWatch metrics polling with simple environment variable reads,
    making the architecture much simpler and more reliable.
    """
    
    def __init__(self):
        """Initialize the environment phase controller."""
        # Log initial values but don't cache them
        initial_phase = int(os.getenv('DEMO_PHASE', '1'))
        initial_tps = int(os.getenv('TARGET_TPS', '100'))
        
        logger.info(f"EnvironmentPhaseController initialized - Initial Phase: {initial_phase}, Initial Target TPS: {initial_tps}")
        logger.info("Phase and TPS will be read dynamically from environment variables")
    
    def get_current_phase_number(self) -> int:
        """Get the current demo phase number from environment variables."""
        return int(os.getenv('DEMO_PHASE', '1'))
    
    def get_target_tps(self) -> int:
        """Get the target TPS for the current phase from environment variables."""
        return int(os.getenv('TARGET_TPS', '100'))
    
    def get_current_phase_info(self) -> Dict:
        """Get complete current phase information from environment variables."""
        return {
            'phase_number': self.get_current_phase_number(),
            'target_tps': self.get_target_tps(),
            'duration_seconds': 120,  # Fixed duration for all phases
            'source': 'environment_variables'
        }
    
    def is_demo_running(self) -> bool:
        """Check if the demo is currently running (always true for deployed containers)."""
        return True
    
    def get_demo_progress(self) -> float:
        """Get demo progress (estimated based on current phase)."""
        progress_map = {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}
        current_phase = self.get_current_phase_number()
        return progress_map.get(current_phase, 0.0)
    
    def calculate_messages_to_generate(self, time_window_seconds: float = 1.0) -> int:
        """Calculate number of messages to generate in the given time window."""
        # Get current values from environment variables
        target_tps = self.get_target_tps()
        per_task_capacity = int(os.getenv('PER_TASK_CAPACITY', '1000'))
        
        # Enforce per-task capacity limit
        # TARGET_TPS should already be limited by Step Functions, but double-check
        effective_tps = min(target_tps, per_task_capacity)
        
        return int(effective_tps * time_window_seconds)
    
    def get_post_type_distribution(self) -> Tuple[float, float, float]:
        """Get distribution of post types for current phase (original, share, reply)."""
        current_phase = self.get_current_phase_number()
        if current_phase <= 2:
            # Early phases: mostly original content
            return (0.7, 0.2, 0.1)
        else:
            # Viral phases: more shares and replies
            return (0.4, 0.4, 0.2)


# Compatibility interface to match the original TrafficPatternController
class EnvironmentTrafficPatternController:
    """
    Compatibility wrapper that provides the same interface as TrafficPatternController
    but gets data from environment variables instead of polling external services.
    """
    
    def __init__(self, config):
        """Initialize with config for compatibility."""
        self.config = config
        self.env_controller = EnvironmentPhaseController()
        self.demo_start_time: Optional[datetime] = None
        
        logger.info("EnvironmentTrafficPatternController initialized (Environment Variable mode)")
    
    def start_demo(self) -> None:
        """
        Mark demo as started (containers are already deployed with correct phase).
        This is a compatibility method - the actual demo start is controlled by Step Functions.
        """
        self.demo_start_time = datetime.utcnow()
        current_phase = self.env_controller.get_current_phase_number()
        logger.info(f"Demo started in phase {current_phase}")
    
    def get_current_phase(self):
        """Get current phase information from environment variables."""
        phase_info = self.env_controller.get_current_phase_info()
        
        # Create a simple phase object for compatibility
        class Phase:
            def __init__(self, info):
                self.phase_number = info.get('phase_number', 1)
                self.target_tps = info.get('target_tps', 100)
                self.duration_seconds = info.get('duration_seconds', 120)
        
        return Phase(phase_info)
    
    def get_target_tps(self) -> int:
        """Get target TPS from environment variables."""
        return self.env_controller.get_target_tps()
    
    def get_demo_progress(self) -> float:
        """Get demo progress from environment variables."""
        return self.env_controller.get_demo_progress()
    
    def get_phase_progress(self) -> float:
        """Get phase progress (estimated - containers don't track phase timing)."""
        return 0.5  # Return midpoint since containers don't track phase timing
    
    def is_demo_complete(self) -> bool:
        """Check if demo is complete (never true for individual containers)."""
        # Individual containers don't know when the overall demo is complete
        # They will be terminated by ECS when Step Functions scales down
        return False
    
    def get_remaining_time(self) -> int:
        """Get remaining time (estimated - containers don't track phase timing)."""
        return 60  # Return estimate since containers don't track phase timing
    
    def calculate_messages_to_generate(self, time_window_seconds: float = 1.0) -> int:
        """Calculate messages to generate from environment variables."""
        return self.env_controller.calculate_messages_to_generate(time_window_seconds)
    
    def get_post_type_distribution(self) -> Tuple[float, float, float]:
        """Get post type distribution from environment variables."""
        return self.env_controller.get_post_type_distribution()