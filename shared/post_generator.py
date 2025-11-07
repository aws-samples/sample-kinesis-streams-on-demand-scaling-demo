"""
Social media post generation logic for the Kinesis On-Demand Demo.
"""

import random
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass

from .models import SocialMediaPost, PostType, GeoLocation
from .config import DemoConfig


@dataclass
class TrafficPhase:
    """Represents a phase in the demo traffic pattern."""
    phase_number: int
    target_tps: int
    duration_seconds: int
    start_time: Optional[datetime] = None
    
    @property
    def end_time(self) -> Optional[datetime]:
        """Calculate end time based on start time and duration."""
        if self.start_time is None:
            return None
        return self.start_time + timedelta(seconds=self.duration_seconds)


class SocialMediaPostGenerator:
    """Generates realistic social media posts for the demo."""
    
    # Sample content templates for different post types
    BREAKING_NEWS_TEMPLATES = [
        "BREAKING: Major tech announcement happening right now! {hashtags}",
        "🚨 URGENT: This changes everything in the industry {hashtags}",
        "JUST IN: Revolutionary breakthrough announced {hashtags}",
        "ALERT: Game-changing news just dropped {hashtags}",
        "BREAKING NEWS: Industry leaders respond to major announcement {hashtags}",
    ]
    
    VIRAL_CONTENT_TEMPLATES = [
        "This is absolutely incredible! Everyone needs to see this {hashtags}",
        "Mind = blown 🤯 This is going to change everything {hashtags}",
        "I can't believe what I'm seeing right now {hashtags}",
        "This is the most amazing thing I've seen all year {hashtags}",
        "EVERYONE needs to know about this immediately {hashtags}",
        "This just made my entire day! Sharing with everyone {hashtags}",
        "I'm literally speechless... this is incredible {hashtags}",
    ]
    
    REACTION_TEMPLATES = [
        "Wow, just saw the news about this! {hashtags}",
        "My thoughts on the latest announcement {hashtags}",
        "Here's what this means for all of us {hashtags}",
        "Quick take on today's big news {hashtags}",
        "This is exactly what we needed to hear {hashtags}",
    ]
    
    # Hashtag pools for different phases
    TRENDING_HASHTAGS = [
        "#BreakingNews", "#TechNews", "#Innovation", "#GameChanger",
        "#Revolutionary", "#Trending", "#Viral", "#MustSee",
        "#Incredible", "#Amazing", "#Unbelievable", "#Shocking"
    ]
    
    TECH_HASHTAGS = [
        "#AI", "#MachineLearning", "#CloudComputing", "#BigData",
        "#IoT", "#Blockchain", "#Cybersecurity", "#DevOps",
        "#Serverless", "#Microservices", "#API", "#Database"
    ]
    
    GENERAL_HASHTAGS = [
        "#News", "#Update", "#Info", "#Share", "#Follow",
        "#Like", "#Comment", "#Retweet", "#Social", "#Media"
    ]
    
    # Geographic locations for realistic distribution
    MAJOR_CITIES = [
        ("New York", "USA", 40.7128, -74.0060),
        ("Los Angeles", "USA", 34.0522, -118.2437),
        ("London", "UK", 51.5074, -0.1278),
        ("Tokyo", "Japan", 35.6762, 139.6503),
        ("Sydney", "Australia", -33.8688, 151.2093),
        ("Toronto", "Canada", 43.6532, -79.3832),
        ("Berlin", "Germany", 52.5200, 13.4050),
        ("Singapore", "Singapore", 1.3521, 103.8198),
        ("Mumbai", "India", 19.0760, 72.8777),
        ("São Paulo", "Brazil", -23.5505, -46.6333),
    ]
    
    # Common usernames patterns
    USERNAME_PREFIXES = [
        "tech", "news", "social", "digital", "cloud", "data",
        "user", "dev", "admin", "pro", "expert", "guru"
    ]
    
    USERNAME_SUFFIXES = [
        "fan", "lover", "expert", "pro", "geek", "ninja",
        "master", "wizard", "guru", "ace", "star", "hero"
    ]
    
    def __init__(self, config: DemoConfig):
        """Initialize the post generator with configuration."""
        self.config = config
        self.random = random.Random()
        self.random.seed(42)  # For reproducible demo content
        
    def generate_post(self, phase: int = 1, post_type: PostType = PostType.ORIGINAL) -> SocialMediaPost:
        """Generate a single social media post for the given phase."""
        # Select content template based on phase
        content = self._generate_content(phase, post_type)
        
        # Generate hashtags based on phase intensity
        hashtags = self._generate_hashtags(phase)
        
        # Generate mentions (more during viral phases)
        mentions = self._generate_mentions(phase)
        
        # Generate geographic location
        location = self._generate_location()
        
        # Generate engagement score based on phase
        engagement_score = self._generate_engagement_score(phase)
        
        # Generate realistic username
        username = self._generate_username()
        user_id = f"user_{self.random.randint(100000, 999999)}"
        
        return SocialMediaPost(
            user_id=user_id,
            username=username,
            content=content,
            hashtags=hashtags,
            mentions=mentions,
            location=location,
            engagement_score=engagement_score,
            post_type=post_type,
            timestamp=datetime.utcnow()
        )
    
    def _generate_content(self, phase: int, post_type: PostType) -> str:
        """Generate content based on demo phase and post type."""
        if phase == 1:  # Baseline phase
            templates = self.REACTION_TEMPLATES
        elif phase == 2:  # Spike phase - breaking news
            templates = self.BREAKING_NEWS_TEMPLATES
        elif phase == 3:  # Peak phase - viral content
            templates = self.VIRAL_CONTENT_TEMPLATES
        else:  # Phase 4 - decline, back to reactions
            templates = self.REACTION_TEMPLATES
        
        template = self.random.choice(templates)
        
        # Add variation with random elements
        variations = [
            "Just heard about this!",
            "This is happening now!",
            "Can't believe this!",
            "Update on the situation:",
            "Latest development:",
            "Breaking update:",
            "This just in:",
            "Major update:",
            "Important news:",
            "Quick update:",
        ]
        
        # Sometimes add a variation prefix (30% chance)
        if self.random.random() < 0.3:
            variation = self.random.choice(variations)
            template = f"{variation} {template}"
        
        # Add random numbers or timestamps for uniqueness (20% chance)
        if self.random.random() < 0.2:
            random_num = self.random.randint(1, 999)
            template = f"{template} #{random_num}"
        
        # Add some random emoji variation (15% chance)
        if self.random.random() < 0.15:
            emojis = ["🔥", "⚡", "🚀", "💯", "👀", "🎯", "💥", "🌟"]
            emoji = self.random.choice(emojis)
            template = f"{template} {emoji}"
        
        # Add post type prefixes
        if post_type == PostType.SHARE:
            template = f"RT: {template}"
        elif post_type == PostType.REPLY:
            usernames = ["techguru", "newsbot", "someone", "user123", "admin"]
            username = self.random.choice(usernames)
            template = f"@{username} {template}"
        
        return template
    
    def _generate_hashtags(self, phase: int) -> List[str]:
        """Generate hashtags based on demo phase."""
        # More hashtags during viral phases
        if phase == 1:
            num_hashtags = self.random.randint(1, 2)
            hashtag_pool = self.GENERAL_HASHTAGS + self.TECH_HASHTAGS
        elif phase == 2:
            num_hashtags = self.random.randint(2, 4)
            hashtag_pool = self.TRENDING_HASHTAGS + self.TECH_HASHTAGS
        elif phase == 3:
            num_hashtags = self.random.randint(3, 6)
            hashtag_pool = self.TRENDING_HASHTAGS + self.VIRAL_CONTENT_TEMPLATES
        else:
            num_hashtags = self.random.randint(1, 3)
            hashtag_pool = self.GENERAL_HASHTAGS + self.TECH_HASHTAGS
        
        # Select unique hashtags
        selected_hashtags = self.random.sample(
            hashtag_pool, 
            min(num_hashtags, len(hashtag_pool))
        )
        
        return selected_hashtags
    
    def _generate_mentions(self, phase: int) -> List[str]:
        """Generate user mentions based on demo phase."""
        # More mentions during viral phases
        if phase <= 2:
            num_mentions = self.random.randint(0, 1)
        else:
            num_mentions = self.random.randint(1, 3)
        
        mentions = []
        for _ in range(num_mentions):
            username = self._generate_username()
            mentions.append(f"@{username}")
        
        return mentions
    
    def _generate_location(self) -> Optional[GeoLocation]:
        """Generate geographic location (70% of posts have location)."""
        if self.random.random() > 0.7:
            return None
        
        city, country, lat, lon = self.random.choice(self.MAJOR_CITIES)
        
        # Add some random variation to coordinates
        lat_variation = self.random.uniform(-0.1, 0.1)
        lon_variation = self.random.uniform(-0.1, 0.1)
        
        return GeoLocation(
            latitude=lat + lat_variation,
            longitude=lon + lon_variation,
            city=city,
            country=country
        )
    
    def _generate_engagement_score(self, phase: int) -> float:
        """Generate engagement score based on demo phase."""
        # Higher engagement during viral phases
        if phase == 1:
            base_score = self.random.uniform(0.1, 2.0)
        elif phase == 2:
            base_score = self.random.uniform(2.0, 8.0)
        elif phase == 3:
            base_score = self.random.uniform(8.0, 20.0)
        else:
            base_score = self.random.uniform(1.0, 5.0)
        
        return round(base_score, 2)
    
    def _generate_username(self) -> str:
        """Generate a realistic username."""
        if self.random.random() < 0.3:
            # Simple numeric username
            return f"user{self.random.randint(1000, 9999)}"
        else:
            # Compound username
            prefix = self.random.choice(self.USERNAME_PREFIXES)
            suffix = self.random.choice(self.USERNAME_SUFFIXES)
            number = self.random.randint(10, 999)
            return f"{prefix}{suffix}{number}"


class TrafficPatternController:
    """Controls traffic patterns for the four demo phases."""
    
    def __init__(self, config: DemoConfig):
        """Initialize the traffic pattern controller."""
        self.config = config
        self.phases = self._create_phases()
        self.demo_start_time: Optional[datetime] = None
        self.current_phase_index = 0
        
    def _create_phases(self) -> List[TrafficPhase]:
        """Create the four demo phases with default values."""
        # Note: In environment variable mode, actual TPS comes from TARGET_TPS env var
        # These are just placeholder values for the internal controller
        phases = []
        default_tps_values = [100, 10000, 50000, 100]  # Phase 1-4 defaults
        
        for i in range(4):
            phase_number = i + 1
            target_tps = default_tps_values[i]
            duration = self.config.get_phase_duration(phase_number)
            
            phases.append(TrafficPhase(
                phase_number=phase_number,
                target_tps=target_tps,
                duration_seconds=duration
            ))
        
        return phases
    
    def start_demo(self) -> None:
        """Start the demo and initialize phase timing."""
        self.demo_start_time = datetime.utcnow()
        self.current_phase_index = 0
        
        # Set start times for all phases
        current_time = self.demo_start_time
        for phase in self.phases:
            phase.start_time = current_time
            current_time = phase.end_time
    
    def get_current_phase(self) -> TrafficPhase:
        """Get the current demo phase based on elapsed time."""
        if self.demo_start_time is None:
            raise RuntimeError("Demo has not been started")
        
        current_time = datetime.utcnow()
        elapsed_seconds = (current_time - self.demo_start_time).total_seconds()
        
        # Find which phase we're currently in
        cumulative_time = 0
        for i, phase in enumerate(self.phases):
            cumulative_time += phase.duration_seconds
            if elapsed_seconds <= cumulative_time:
                self.current_phase_index = i
                return phase
        
        # Demo is complete, return last phase
        self.current_phase_index = len(self.phases) - 1
        return self.phases[-1]
    
    def get_target_tps(self) -> int:
        """Get target TPS for current phase."""
        current_phase = self.get_current_phase()
        return current_phase.target_tps
    
    def get_phase_progress(self) -> float:
        """Get progress through current phase (0.0 to 1.0)."""
        if self.demo_start_time is None:
            return 0.0
        
        current_phase = self.get_current_phase()
        if current_phase.start_time is None:
            return 0.0
        
        current_time = datetime.utcnow()
        elapsed_in_phase = (current_time - current_phase.start_time).total_seconds()
        
        return min(1.0, elapsed_in_phase / current_phase.duration_seconds)
    
    def get_demo_progress(self) -> float:
        """Get overall demo progress (0.0 to 1.0)."""
        if self.demo_start_time is None:
            return 0.0
        
        current_time = datetime.utcnow()
        elapsed_seconds = (current_time - self.demo_start_time).total_seconds()
        total_duration = self.config.get_total_demo_duration()
        
        return min(1.0, elapsed_seconds / total_duration)
    
    def is_demo_complete(self) -> bool:
        """Check if the demo is complete."""
        return self.get_demo_progress() >= 1.0
    
    def get_remaining_time(self) -> int:
        """Get remaining time in current phase (seconds)."""
        if self.demo_start_time is None:
            return 0
        
        current_phase = self.get_current_phase()
        if current_phase.start_time is None:
            return 0
        
        current_time = datetime.utcnow()
        elapsed_in_phase = (current_time - current_phase.start_time).total_seconds()
        
        return max(0, int(current_phase.duration_seconds - elapsed_in_phase))
    
    def calculate_messages_to_generate(self, time_window_seconds: float = 1.0) -> int:
        """Calculate number of messages to generate in the given time window."""
        target_tps = self.get_target_tps()
        return int(target_tps * time_window_seconds)
    
    def get_post_type_distribution(self) -> Tuple[float, float, float]:
        """Get distribution of post types for current phase (original, share, reply)."""
        if self.demo_start_time is None:
            # Default distribution if demo hasn't started
            return (0.7, 0.2, 0.1)
            
        current_phase = self.get_current_phase()
        
        if current_phase.phase_number <= 2:
            # Early phases: mostly original content
            return (0.7, 0.2, 0.1)
        else:
            # Viral phases: more shares and replies
            return (0.4, 0.4, 0.2)