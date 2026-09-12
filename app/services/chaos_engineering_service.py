"""Chaos Engineering service for resilience testing."""

import asyncio
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Callable
from app.database import Database
from app.services import get_redis
from app.utils.logging import get_logger
from app.config import get_settings

logger = get_logger(__name__)


class ChaosExperimentType(Enum):
    LATENCY_INJECTION = "latency_injection"
    ERROR_INJECTION = "error_injection"
    DB_CONNECTION_FAILURE = "db_connection_failure"
    REDIS_CONNECTION_FAILURE = "redis_connection_failure"
    PARTIAL_OUTAGE = "partial_outage"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"


class ExperimentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class ChaosExperiment:
    experiment_id: str
    name: str
    type: ChaosExperimentType
    config: Dict
    status: ExperimentStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_seconds: Optional[float] = None
    results: Optional[Dict] = None
    error: Optional[str] = None


@dataclass
class ExperimentResult:
    experiment_id: str
    success: bool
    metrics_before: Dict
    metrics_after: Dict
    errors: List[str]
    observations: List[str]
    recovery_time_seconds: Optional[float] = None


class ChaosEngineeringService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()
        self._redis = None
        self._experiments: Dict[str, ChaosExperiment] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._injection_enabled = False
        self._latency_ms = 0
        self._error_rate = 0.0
        self._db_failure = False
        self._redis_failure = False

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    # ===== Experiment Management =====
    def create_experiment(
        self,
        name: str,
        exp_type: ChaosExperimentType,
        config: Dict,
    ) -> ChaosExperiment:
        """Create a new chaos experiment."""
        import uuid
        experiment_id = str(uuid.uuid4())[:8]

        experiment = ChaosExperiment(
            experiment_id=experiment_id,
            name=name,
            type=exp_type,
            config=config,
            status=ExperimentStatus.PENDING,
            created_at=time.time(),
        )
        self._experiments[experiment_id] = experiment
        logger.info("chaos_experiment_created", experiment_id=experiment_id, name=name, type=exp_type.value)
        return experiment

    async def run_experiment(self, experiment_id: str) -> ExperimentResult:
        """Run a chaos experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        if experiment.status == ExperimentStatus.RUNNING:
            raise ValueError("Experiment already running")

        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = time.time()

        # Collect metrics before
        metrics_before = await self._collect_metrics()

        # Run the experiment
        try:
            await self._run_experiment_impl(experiment)
            experiment.status = ExperimentStatus.COMPLETED
        except Exception as e:
            experiment.status = ExperimentStatus.FAILED
            experiment.error = str(e)
            logger.error("chaos_experiment_failed", experiment_id=experiment_id, error=str(e))
            raise
        finally:
            experiment.completed_at = time.time()
            experiment.duration_seconds = experiment.completed_at - experiment.started_at

        # Collect metrics after
        metrics_after = await self._collect_metrics()

        # Analyze results
        result = ExperimentResult(
            experiment_id=experiment_id,
            success=experiment.status == ExperimentStatus.COMPLETED,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            errors=[experiment.error] if experiment.error else [],
            observations=self._analyze_results(metrics_before, metrics_after, experiment),
            recovery_time_seconds=await self._measure_recovery_time(experiment),
        )

        experiment.results = {
            "success": result.success,
            "metrics_before": result.metrics_before,
            "metrics_after": result.metrics_after,
            "errors": result.errors,
            "observations": result.observations,
            "recovery_time_seconds": result.recovery_time_seconds,
        }

        logger.info("chaos_experiment_completed", experiment_id=experiment_id, success=result.success)
        return result

    async def _run_experiment_impl(self, experiment: ChaosExperiment) -> None:
        """Execute the actual experiment based on type."""
        config = experiment.config

        if experiment.type == ChaosExperimentType.LATENCY_INJECTION:
            self._latency_ms = config.get("latency_ms", 1000)
            self._injection_enabled = True
            duration = config.get("duration_seconds", 60)
            await asyncio.sleep(duration)
            self._latency_ms = 0
            self._injection_enabled = False

        elif experiment.type == ChaosExperimentType.ERROR_INJECTION:
            self._error_rate = config.get("error_rate", 0.1)
            self._injection_enabled = True
            duration = config.get("duration_seconds", 60)
            await asyncio.sleep(duration)
            self._error_rate = 0.0
            self._injection_enabled = False

        elif experiment.type == ChaosExperimentType.DB_CONNECTION_FAILURE:
            self._db_failure = True
            duration = config.get("duration_seconds", 30)
            await asyncio.sleep(duration)
            self._db_failure = False

        elif experiment.type == ChaosExperimentType.REDIS_CONNECTION_FAILURE:
            self._redis_failure = True
            duration = config.get("duration_seconds", 30)
            await asyncio.sleep(duration)
            self._redis_failure = False

        elif experiment.type == ChaosExperimentType.PARTIAL_OUTAGE:
            # Simulate partial outage - some requests fail
            self._injection_enabled = True
            self._error_rate = config.get("error_rate", 0.5)
            self._latency_ms = config.get("latency_ms", 5000)
            duration = config.get("duration_seconds", 60)
            await asyncio.sleep(duration)
            self._error_rate = 0.0
            self._latency_ms = 0
            self._injection_enabled = False

        elif experiment.type == ChaosExperimentType.RESOURCE_EXHAUSTION:
            # Simulate high CPU/memory
            self._latency_ms = config.get("latency_ms", 2000)
            self._injection_enabled = True
            duration = config.get("duration_seconds", 120)
            await asyncio.sleep(duration)
            self._latency_ms = 0
            self._injection_enabled = False

        elif experiment.type == ChaosExperimentType.NETWORK_PARTITION:
            # Simulate network issues
            self._redis_failure = True
            self._db_failure = True
            duration = config.get("duration_seconds", 30)
            await asyncio.sleep(duration)
            self._redis_failure = False
            self._db_failure = False

    async def abort_experiment(self, experiment_id: str) -> bool:
        """Abort a running experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment or experiment.status != ExperimentStatus.RUNNING:
            return False

        # Reset injection flags
        self._injection_enabled = False
        self._latency_ms = 0
        self._error_rate = 0.0
        self._db_failure = False
        self._redis_failure = False

        experiment.status = ExperimentStatus.ABORTED
        experiment.completed_at = time.time()
        experiment.duration_seconds = experiment.completed_at - experiment.started_at
        experiment.error = "Aborted by user"

        logger.warning("chaos_experiment_aborted", experiment_id=experiment_id)
        return True

    def get_experiment(self, experiment_id: str) -> Optional[ChaosExperiment]:
        return self._experiments.get(experiment_id)

    def list_experiments(self) -> List[ChaosExperiment]:
        return list(self._experiments.values())

    # ===== Injection Methods (called by middleware) =====
    async def maybe_inject_latency(self) -> None:
        """Inject latency if enabled."""
        if self._injection_enabled and self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

    async def maybe_inject_error(self) -> bool:
        """Inject error if enabled. Returns True if error should be raised."""
        if self._injection_enabled and self._error_rate > 0:
            return random.random() < self._error_rate
        return False

    async def check_db_failure(self) -> bool:
        """Check if DB failure is injected."""
        return self._db_failure

    async def check_redis_failure(self) -> bool:
        """Check if Redis failure is injected."""
        return self._redis_failure

    # ===== Metrics Collection =====
    async def _collect_metrics(self) -> Dict:
        """Collect current system metrics."""
        redis = await self.redis
        return {
            "timestamp": time.time(),
            "active_users": await redis.get("metrics:active_users_daily") or 0,
            "dig_rate": await redis.get("metrics:dig_rate") or 0,
            "error_rate": await redis.get("metrics:error_rate") or 0,
            "avg_latency": await redis.get("metrics:avg_latency") or 0,
            "db_pool_usage": await redis.get("metrics:db_pool_usage") or 0,
            "cache_hit_rate": await redis.get("metrics:cache_hit_rate") or 0,
        }

    def _analyze_results(self, before: Dict, after: Dict, experiment: ChaosExperiment) -> List[str]:
        """Analyze experiment results."""
        observations = []

        # Latency change
        if "avg_latency" in before and "avg_latency" in after:
            change = after["avg_latency"] - before["avg_latency"]
            if change > 100:
                observations.append(f"Latency increased by {change:.0f}ms")

        # Error rate change
        if "error_rate" in before and "error_rate" in after:
            change = after["error_rate"] - before["error_rate"]
            if change > 0.01:
                observations.append(f"Error rate increased by {change*100:.1f}%")

        # Dig rate change
        if "dig_rate" in before and "dig_rate" in after:
            change = after["dig_rate"] - before["dig_rate"]
            if change < -10:
                observations.append(f"Dig rate dropped by {abs(change):.0f}/min")

        # Recovery observations
        if experiment.type == ChaosExperimentType.DB_CONNECTION_FAILURE:
            observations.append("DB connection failure simulated - check retry logic")
        elif experiment.type == ChaosExperimentType.REDIS_CONNECTION_FAILURE:
            observations.append("Redis failure simulated - check fallback behavior")

        return observations

    async def _measure_recovery_time(self, experiment: ChaosExperiment) -> Optional[float]:
        """Measure how long it takes to recover after experiment."""
        # Wait a bit and check if metrics recover
        await asyncio.sleep(5)
        metrics_after = await self._collect_metrics()
        metrics_before = experiment.results.get("metrics_before", {}) if experiment.results else {}

        # Simple recovery check
        if "avg_latency" in metrics_before and "avg_latency" in metrics_after:
            if abs(metrics_after["avg_latency"] - metrics_before["avg_latency"]) < 50:
                return 5.0  # Recovered in ~5 seconds

        return None

    # ===== Predefined Experiment Templates =====
    @staticmethod
    def get_predefined_experiments() -> List[Dict]:
        """Get list of predefined experiment templates."""
        return [
            {
                "name": "Latency Spike Test",
                "type": "latency_injection",
                "description": "Inject 2 second latency for 60 seconds to test timeout handling",
                "config": {"latency_ms": 2000, "duration_seconds": 60},
            },
            {
                "name": "Error Rate Test",
                "type": "error_injection",
                "description": "Inject 10% error rate for 60 seconds",
                "config": {"error_rate": 0.1, "duration_seconds": 60},
            },
            {
                "name": "DB Connection Failure",
                "type": "db_connection_failure",
                "description": "Simulate DB connection failure for 30 seconds",
                "config": {"duration_seconds": 30},
            },
            {
                "name": "Redis Failure",
                "type": "redis_connection_failure",
                "description": "Simulate Redis failure for 30 seconds",
                "config": {"duration_seconds": 30},
            },
            {
                "name": "Partial Outage",
                "type": "partial_outage",
                "description": "Simulate partial outage with 50% errors and high latency",
                "config": {"error_rate": 0.5, "latency_ms": 5000, "duration_seconds": 60},
            },
            {
                "name": "Resource Exhaustion",
                "type": "resource_exhaustion",
                "description": "Simulate high resource usage for 2 minutes",
                "config": {"latency_ms": 2000, "duration_seconds": 120},
            },
            {
                "name": "Network Partition",
                "type": "network_partition",
                "description": "Simulate network partition affecting both DB and Redis",
                "config": {"duration_seconds": 30},
            },
        ]


# Global instance
_chaos_service = None


def get_chaos_service(db: Database = None) -> ChaosEngineeringService:
    global _chaos_service
    if _chaos_service is None and db is not None:
        _chaos_service = ChaosEngineeringService(db)
    return _chaos_service


# Middleware for chaos injection
class ChaosInjectionMiddleware:
    """Middleware that injects chaos based on running experiments."""

    def __init__(self, chaos_service: ChaosEngineeringService):
        self.chaos_service = chaos_service

    async def __call__(self, handler, event, data):
        # Inject latency
        await self.chaos_service.maybe_inject_latency()

        # Inject errors
        if await self.chaos_service.maybe_inject_error():
            from app.exceptions import DatabaseError
            raise DatabaseError("Chaos engineering: injected error")

        # Check DB failure
        if await self.chaos_service.check_db_failure():
            from app.exceptions import DatabaseError
            raise DatabaseError("Chaos engineering: DB failure injected")

        return await handler(event, data)