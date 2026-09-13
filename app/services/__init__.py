"""Services package."""

# Core services
from app.services.core import (
    UserService,
    DigService,
    DailyBonusService,
    CleanupService,
    RedisService,
    get_dig_service,
    get_daily_bonus_service,
    get_cleanup_service,
    get_redis,
    close_redis,
)

# Feature services
from app.services.features import (
    AchievementService,
    get_achievement_service,
    Achievement,
    ClanService,
    get_clan_service,
    Clan,
    ClanMember,
    ClanInvite,
    MetricsService,
    get_metrics_service,
    MLRecommendationService,
    get_ml_service,
    UserProfile,
    Recommendation,
)

# Chaos engineering
from app.services.chaos import (
    ChaosEngineeringService,
    get_chaos_service,
    ChaosExperimentType,
    ExperimentStatus,
    ChaosExperiment,
    ExperimentResult,
    ChaosInjectionMiddleware,
    enable_chaos,
    disable_chaos,
    set_chaos_experiment,
    set_chaos_intensity,
    get_chaos_status,
)

__all__ = [
    # Core
    "UserService",
    "DigService",
    "DailyBonusService",
    "CleanupService",
    "RedisService",
    "get_dig_service",
    "get_daily_bonus_service",
    "get_cleanup_service",
    "get_redis",
    "close_redis",
    # Features
    "AchievementService",
    "get_achievement_service",
    "Achievement",
    "ClanService",
    "get_clan_service",
    "Clan",
    "ClanMember",
    "ClanInvite",
    "MetricsService",
    "get_metrics_service",
    "MLRecommendationService",
    "get_ml_service",
    "UserProfile",
    "Recommendation",
    # Chaos
    "ChaosEngineeringService",
    "get_chaos_service",
    "ChaosExperimentType",
    "ExperimentStatus",
    "ChaosExperiment",
    "ExperimentResult",
    "ChaosInjectionMiddleware",
    "enable_chaos",
    "disable_chaos",
    "set_chaos_experiment",
    "set_chaos_intensity",
    "get_chaos_status",
]