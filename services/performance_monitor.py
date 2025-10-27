"""
Database Query Performance Monitor

Provides decorators and utilities for monitoring database query performance.
Logs slow queries and tracks performance metrics.
"""

import time
from functools import wraps

from logging_config import logger


class QueryPerformanceMonitor:
    """Monitor and log database query performance"""

    # Threshold in seconds for what constitutes a "slow" query
    SLOW_QUERY_THRESHOLD = 1.0

    @staticmethod
    def monitor_query(operation_name: str, slow_threshold: float | None = None):
        """
        Decorator to monitor database query performance

        Args:
            operation_name: Descriptive name of the operation being monitored
            slow_threshold: Override default slow query threshold in seconds

        Usage:
            @monitor_query("fetch_match_standings")
            async def fetch_standings(t_alias, s_alias):
                # Database query here
                pass
        """
        threshold = slow_threshold or QueryPerformanceMonitor.SLOW_QUERY_THRESHOLD

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start_time

                    if elapsed > threshold:
                        logger.warning(
                            f"Slow query detected: {operation_name}",
                            extra={
                                "operation": operation_name,
                                "duration_seconds": round(elapsed, 3),
                                "function": func.__name__,
                                "threshold": threshold,
                            },
                        )
                    else:
                        logger.debug(
                            f"Query completed: {operation_name}",
                            extra={
                                "operation": operation_name,
                                "duration_seconds": round(elapsed, 3),
                            },
                        )

                    return result
                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"Query failed: {operation_name}",
                        extra={
                            "operation": operation_name,
                            "duration_seconds": round(elapsed, 3),
                            "error": str(e),
                        },
                    )
                    raise

            return wrapper

        return decorator

    @staticmethod
    def log_query_plan(collection_name: str, filter_dict: dict, explanation: dict):
        """
        Log MongoDB query execution plan for analysis

        Args:
            collection_name: Name of the collection being queried
            filter_dict: The query filter used
            explanation: MongoDB explain() output
        """
        logger.info(
            f"Query execution plan for {collection_name}",
            extra={
                "collection": collection_name,
                "filter": str(filter_dict),
                "execution_stats": explanation.get("executionStats", {}),
                "winning_plan": explanation.get("queryPlanner", {}).get("winningPlan", {}),
            },
        )


# Convenience function for direct usage
monitor_query = QueryPerformanceMonitor.monitor_query
