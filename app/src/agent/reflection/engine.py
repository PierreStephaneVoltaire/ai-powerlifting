"""Core reflection engine for metacognitive analysis.

Implements Part4 of plan.md - The Reflection Engine.

The reflection engine runs:
- Post-session after substantive conversations (>5 exchanges)
- Periodically every6 hours
- On-demand via /reflect command
- When thresholds are hit (uncategorized facts, gaps without criteria, etc.)

The reflection cycle includes:
1. Pattern Detection - Cluster topics, detect temporal patterns
2. Opinion Formation - Form agent positions on user opinions
3. Capability Gap Analysis - Aggregate gaps, compute priority
4. Meta-Analysis - Category health, store metrics
5. Operator Growth Tracking - Misconception trends, skill progression
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Any, Optional

from config import (
    REFLECTION_ENABLED,
    REFLECTION_PERIODIC_HOURS,
    REFLECTION_POST_SESSION_MIN_TURNS,
    REFLECTION_THRESHOLD_UNCATEGORIZED,
    REFLECTION_THRESHOLD_GAPS_NO_CRITERIA,
    REFLECTION_THRESHOLD_OPINIONS_NO_RESPONSE,
    CAPABILITY_GAP_PROMOTION_THRESHOLD,
    REFLECTION_MODEL,
    REFLECTION_CONTEXT_ID,
)
from agent.prompts.loader import load_prompt

if TYPE_CHECKING:
    from memory.user_facts import UserFactStore
    import httpx

logger = logging.getLogger(__name__)

# Global reflection engine instance
_reflection_engine: Optional["ReflectionEngine"] = None


def get_reflection_engine() -> Optional["ReflectionEngine"]:
    """Get the global reflection engine instance."""
    return _reflection_engine


class ReflectionEngine:
    """Core reflection engine for metacognitive analysis.
    
    Runs periodic and post-session reflection cycles to:
    - Detect patterns in operator behavior
    - Form agent opinions on user-stated positions
    - Analyze capability gaps for tool suggestions
    - Track operator growth and learning
    
    Example:
        >>> engine = ReflectionEngine(store, http_client)
        >>> engine.start()
        >>> # ... runs in background ...
        >>> engine.stop()
    """
    
    def __init__(
        self,
        store: "UserFactStore",
        http_client: "httpx.AsyncClient",
        llm_model: str = None,
    ):
        """Initialize the reflection engine.
        
        Args:
            store: UserFactStore for reading/writing facts
            http_client: HTTP client for LLM calls
            llm_model: Model to use for reflection analysis (default: from REFLECTION_MODEL env var)
        """
        # Use config default if no model specified
        if llm_model is None:
            from flow.model_catalog import load_model_ids

            model_ids = load_model_ids()
            candidate = REFLECTION_MODEL.replace("openrouter/", "")
            llm_model = candidate if candidate in model_ids else (model_ids[0] if model_ids else candidate)
        self.store = store
        self.http_client = http_client
        self.llm_model = llm_model
        self._task: asyncio.Task | None = None
        self._last_reflection: datetime | None = None
        
        # Import sub-components lazily to avoid circular imports
        from .pattern_detector import PatternDetector
        from .opinion_formation import OpinionFormer
        from .meta_analysis import MetaAnalyzer
        from .growth_tracker import GrowthTracker
        
        self.pattern_detector = PatternDetector(store)
        self.opinion_former = OpinionFormer(store, http_client, llm_model)
        self.meta_analyzer = MetaAnalyzer(store)
        self.growth_tracker = GrowthTracker(store)
    
    def start(self) -> None:
        """Start the reflection background loop."""
        if not REFLECTION_ENABLED:
            logger.info("[Reflection] Disabled via config")
            return
        
        if self._task is not None:
            logger.warning("[Reflection] Already running")
            return
        
        self._task = asyncio.create_task(self._loop())
        logger.info("[Reflection] Engine started")
    
    def stop(self) -> None:
        """Stop the reflection background loop."""
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("[Reflection] Engine stopped")
    
    async def _loop(self) -> None:
        """Main reflection loop - runs every REFLECTION_PERIODIC_HOURS."""
        interval_seconds = REFLECTION_PERIODIC_HOURS * 3600
        
        while True:
            try:
                # Check if we should run based on thresholds
                if self._should_trigger_threshold():
                    logger.info("[Reflection] Threshold trigger detected")
                    await self.run_reflection_cycle(reason="threshold")
                else:
                    # Run periodic reflection
                    await self.run_reflection_cycle(reason="periodic")
                
                self._last_reflection = datetime.now(timezone.utc)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[Reflection] Cycle failed: {e}")
            
            await asyncio.sleep(interval_seconds)
    
    def _should_trigger_threshold(self) -> bool:
        """Check if any threshold conditions are met.
        
        Returns:
            True if reflection should be triggered by threshold
        """
        try:
            from memory.user_facts import FactCategory
            ctx = REFLECTION_CONTEXT_ID

            # Check uncategorized facts pressure
            # (facts that were hard to categorize)
            meta_obs = self.store.list_by_category(ctx, FactCategory.MODEL_ASSESSMENT)
            if len(meta_obs) >= REFLECTION_THRESHOLD_UNCATEGORIZED:
                logger.info(f"[Reflection] Threshold: {len(meta_obs)} uncategorized facts")
                return True

            # Check capability gaps without acceptance criteria
            gaps = self.store.list_by_category(ctx, FactCategory.CAPABILITY_GAP)
            gaps_no_criteria = [
                g for g in gaps
                if not g.metadata.get("acceptance_criteria")
            ]
            if len(gaps_no_criteria) >= REFLECTION_THRESHOLD_GAPS_NO_CRITERIA:
                logger.info(f"[Reflection] Threshold: {len(gaps_no_criteria)} gaps without criteria")
                return True

            # Check opinions without agent responses
            opinions = self.store.list_by_category(ctx, FactCategory.OPINION)
            opinions_no_response = [
                o for o in opinions
                if not o.metadata.get("agent_response")
            ]
            if len(opinions_no_response) >= REFLECTION_THRESHOLD_OPINIONS_NO_RESPONSE:
                logger.info(f"[Reflection] Threshold: {len(opinions_no_response)} opinions without response")
                return True

            return False
            
        except Exception as e:
            logger.warning(f"[Reflection] Threshold check failed: {e}")
            return False
    
    async def run_reflection_cycle(
        self,
        reason: str = "periodic",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a complete reflection cycle.
        
        This is the main entry point for reflection, called:
        - Periodically by the background loop
        - After substantive sessions (post-session)
        - On-demand via /reflect command
        
        Args:
            reason: Why reflection is running ("periodic", "post_session", "on_demand", "threshold")
            session_id: Optional session ID for post-session reflection
            
        Returns:
            Summary of reflection results
        """
        logger.info(f"[Reflection] Starting cycle (reason={reason})")
        
        results = {
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patterns_detected": 0,
            "opinions_formed": 0,
            "gaps_promoted": 0,
            "meta_observations": 0,
            "growth_suggestions": 0,
        }
        
        try:
            #1. Pattern Detection
            patterns = await self.pattern_detector.detect_patterns()
            results["patterns_detected"] = len(patterns)
            logger.info(f"[Reflection] Detected {len(patterns)} patterns")
            
            #2. Opinion Formation
            opinions = await self.opinion_former.form_opinions()
            results["opinions_formed"] = len(opinions)
            logger.info(f"[Reflection] Formed {len(opinions)} opinions")
            
            #3. Capability Gap Analysis & Promotion
            promoted = await self._analyze_capability_gaps()
            results["gaps_promoted"] = len(promoted)
            logger.info(f"[Reflection] Promoted {len(promoted)} gaps to tool suggestions")
            
            #4. Meta-Analysis
            metrics = self.meta_analyzer.analyze()
            results["meta_observations"] = len(metrics.get("suggested_categories", []))
            logger.info(f"[Reflection] Meta-analysis: {metrics.get('total_facts', 0)} facts")
            
            #5. Growth Tracking
            growth = self.growth_tracker.generate_growth_report(days_back=30)
            results["growth_suggestions"] = len(growth.get("suggestions", []))
            
            # Store reflection summary as meta_observation
            await self._store_reflection_summary(results, session_id)
            
            logger.info(f"[Reflection] Cycle complete: {results}")
            
        except Exception as e:
            logger.error(f"[Reflection] Cycle error: {e}")
            results["error"] = str(e)
        
        return results
    
    async def run_post_session(
        self,
        session_id: str,
        turn_count: int,
        summary: str | None = None,
    ) -> dict[str, Any] | None:
        """Run post-session reflection if threshold met.
        
        Called after substantive conversations (>5 turns by default).
        
        Args:
            session_id: The conversation ID
            turn_count: Number of turns in the session
            summary: Optional session summary
            
        Returns:
            Reflection results or None if not triggered
        """
        if turn_count < REFLECTION_POST_SESSION_MIN_TURNS:
            logger.debug(f"[Reflection] Skipping post-session: only {turn_count} turns")
            return None
        
        logger.info(f"[Reflection] Post-session reflection for {session_id}")
        
        return await self.run_reflection_cycle(
            reason="post_session",
            session_id=session_id,
        )
    
    async def _analyze_capability_gaps(self) -> list[str]:
        """Analyze capability gaps and promote high-frequency ones.
        
        Promotes gaps with trigger_count >= CAPABILITY_GAP_PROMOTION_THRESHOLD
        to tool suggestions with acceptance criteria.
        
        Returns:
            List of promoted gap IDs
        """
        from memory.user_facts import FactCategory, FactSource, UserFact, CapabilityGap
        import math
        
        promoted_ids = []
        
        try:
            ctx = REFLECTION_CONTEXT_ID
            gaps = self.store.list_by_category(ctx, FactCategory.CAPABILITY_GAP)

            for gap_fact in gaps:
                metadata = gap_fact.metadata or {}
                trigger_count = metadata.get("trigger_count", 0)

                # Check promotion threshold
                if trigger_count < CAPABILITY_GAP_PROMOTION_THRESHOLD:
                    continue

                if metadata.get("promoted", False):
                    continue  # Already promoted

                # Compute priority score
                # priority = (trigger_count / max_triggers) * 0.4
                #          + recency_weight * 0.3
                #          + impact_estimate * 0.3
                trigger_component = min(trigger_count / 20.0, 1.0) * 0.4

                # Recency weight with exponential decay (lambda = 0.05)
                last_seen = metadata.get("last_seen", "")
                if last_seen:
                    try:
                        last_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                        days_since = (datetime.now(timezone.utc) - last_dt).days
                        recency_weight = math.exp(-0.05 * days_since)
                    except:
                        recency_weight = 0.5
                else:
                    recency_weight = 0.5
                recency_component = recency_weight * 0.3

                # Impact estimate based on status and workaround
                status = metadata.get("status", "open")
                workaround = metadata.get("workaround")
                if status == "resolved":
                    impact = 0.1
                elif workaround:
                    impact = 0.5
                else:
                    impact = 0.8
                impact_component = impact * 0.3

                priority_score = trigger_component + recency_component + impact_component

                # Generate acceptance criteria (simplified - could use LLM)
                content = gap_fact.content
                contexts = metadata.get("trigger_contexts", [])
                acceptance_criteria = self._generate_acceptance_criteria(content, contexts)

                # Create tool suggestion
                self.store.add(
                    context_id=ctx,
                    content=f"Tool suggestion for: {content}",
                    category=FactCategory.TOOL_SUGGESTION,
                    source=FactSource.MODEL_OBSERVED,
                    confidence=0.8,
                    metadata={
                        "source_gap_id": gap_fact.id,
                        "acceptance_criteria": acceptance_criteria,
                        "trigger_count": trigger_count,
                        "priority_score": priority_score,
                        "example_contexts": contexts[:5],
                        "created_from_reflection": True,
                    }
                )

                promoted_ids.append(gap_fact.id)
                logger.info(f"[Reflection] Promoted gap {gap_fact.id} (priority={priority_score:.2f})")
                
        except Exception as e:
            logger.error(f"[Reflection] Gap analysis failed: {e}")
        
        return promoted_ids
    
    def _generate_acceptance_criteria(
        self,
        gap_content: str,
        contexts: list[str],
    ) -> list[str]:
        """Generate acceptance criteria for a capability gap.
        
        This is a simplified implementation. In production, this could
        use an LLM to generate more specific criteria.
        
        Args:
            gap_content: Description of what the agent cannot do
            contexts: Example contexts where this gap was hit
            
        Returns:
            List of acceptance criteria
        """
        criteria = []
        
        # Generic criteria based on gap type
        gap_lower = gap_content.lower()
        
        if "math" in gap_lower or "calculation" in gap_lower or "arithmetic" in gap_lower:
            criteria = [
                "Accepts arbitrary arithmetic expressions",
                "Returns exact results for integer operations",
                "Handles floating point with specified precision",
                "Supports common mathematical functions",
            ]
        elif "email" in gap_lower or "mail" in gap_lower:
            criteria = [
                "Can send emails to specified recipients",
                "Supports subject and body content",
                "Handles attachments if needed",
                "Provides delivery status feedback",
            ]
        elif "calendar" in gap_lower or "schedule" in gap_lower:
            criteria = [
                "Can create calendar events",
                "Can query existing events",
                "Supports recurring events",
                "Handles timezone conversion",
            ]
        elif "web" in gap_lower or "browse" in gap_lower or "http" in gap_lower:
            criteria = [
                "Can make HTTP requests to external APIs",
                "Handles authentication headers",
                "Parses JSON/XML responses",
                "Respects rate limits",
            ]
        else:
            # Generic criteria
            criteria = [
                f"Can: {gap_content}",
                "Handles errors gracefully",
                "Provides clear feedback to operator",
            ]
            # Add context-based criteria
            for ctx in contexts[:2]:
                criteria.append(f"Handles scenario: {ctx[:80]}...")
        
        return criteria
    
    async def _store_reflection_summary(
        self,
        results: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        """Store reflection summary as a meta_observation."""
        from memory.user_facts import FactCategory, FactSource

        try:
            self.store.add(
                context_id=REFLECTION_CONTEXT_ID,
                content=f"Reflection cycle: {results.get('reason', 'unknown')} - "
                       f"{results.get('patterns_detected', 0)} patterns, "
                       f"{results.get('opinions_formed', 0)} opinions, "
                       f"{results.get('gaps_promoted', 0)} gaps promoted",
                category=FactCategory.SESSION_REFLECTION,
                source=FactSource.MODEL_OBSERVED,
                confidence=0.8,
                metadata={
                    "reflection_results": results,
                    "session_id": session_id,
                }
            )

        except Exception as e:
            logger.warning(f"[Reflection] Failed to store summary: {e}")
    
    def get_status(self) -> dict[str, Any]:
        """Get current reflection engine status.
        
        Returns:
            Status dict with running state, last reflection time, etc.
        """
        return {
            "enabled": REFLECTION_ENABLED,
            "running": self._task is not None and not self._task.done(),
            "last_reflection": self._last_reflection.isoformat() if self._last_reflection else None,
            "periodic_hours": REFLECTION_PERIODIC_HOURS,
            "post_session_min_turns": REFLECTION_POST_SESSION_MIN_TURNS,
        }
