"""Opinion formation for reflection engine.

Implements Part4 of plan.md - Opinion Formation.

Reviews user opinions without agent responses and forms
agent positions with reasoning, storing as opinion_pairs.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Dict
from dataclasses import dataclass

from config import REFLECTION_MODEL
from agent.prompts.loader import render_template, load_prompt

from config import REFLECTION_CONTEXT_ID

if TYPE_CHECKING:
    from memory.user_facts import UserFactStore
    import httpx

logger = logging.getLogger(__name__)


class OpinionFormer:
    """Forms agent opinions on user-stated positions.
    
    Reviews opinions logged in the fact store and generates
    agent responses with reasoning.
    
    Example:
        >>> former = OpinionFormer(store, http_client, model)
        >>> opinions = await former.form_opinions()
        >>> for op in opinions:
        ...     print(f"{op['topic']}: {op['agent_position']}")
    """
    
    def __init__(
        self,
        store: "UserFactStore",
        http_client: "httpx.AsyncClient",
        llm_model: str = None,
    ):
        """Initialize opinion former.
        
        Args:
            store: UserFactStore for reading/writing facts
            http_client: HTTP client for LLM calls
            llm_model: Model to use for opinion formation (default: from REFLECTION_MODEL env var)
        """
        # Use config default if no model specified
        if llm_model is None:
            from models.router import resolve_preset_to_model
            llm_model = resolve_preset_to_model(REFLECTION_MODEL)

        self.store = store
        self.http_client = http_client
        self.llm_model = llm_model
    
    async def form_opinions(self) -> List[Dict[str, Any]]:
        """Form agent opinions on user-stated positions.
        
        Finds opinions without agent responses and generates
        positions with reasoning.
        
        Returns:
            List of formed opinions with topic, position, reasoning
        """
        from memory.user_facts import FactCategory, FactSource, UserFact, OpinionPair
        
        formed_opinions = []
        
        try:
            ctx = REFLECTION_CONTEXT_ID
            # Get all opinions
            opinions = self.store.list_by_category(ctx, FactCategory.OPINION)

            # Also check opinion_pairs that might need evolution
            pairs = self.store.list_by_category(ctx, FactCategory.OPINION_PAIR)
            
            # Find opinions without agent responses
            for opinion in opinions:
                # Check if we already have an opinion_pair for this
                existing_pair = self._find_opinion_pair(opinion.content, pairs)
                
                if existing_pair:
                    # Check if opinion needs evolution (new evidence)
                    continue
                
                # Form new opinion
                try:
                    formed = await self._form_single_opinion(
                        topic=opinion.content,
                        user_position=opinion.content,
                    )
                    
                    if formed:
                        formed_opinions.append(formed)
                        
                except Exception as e:
                    logger.warning(f"[OpinionFormer] Failed to form opinion: {e}")
                    
            logger.info(f"[OpinionFormer] Formed {len(formed_opinions)} opinions")
            
        except Exception as e:
            logger.error(f"[OpinionFormer] Opinion formation failed: {e}")
        
        return formed_opinions
    
    async def _form_single_opinion(
        self,
        topic: str,
        user_position: str,
    ) -> Dict[str, Any] | None:
        """Form an agent opinion on a single topic.
        
        Args:
            topic: The topic/subject
            user_position: What the operator believes/said
            
        Returns:
            Formed opinion dict or None if formation failed
        """
        from memory.user_facts import FactCategory, FactSource, UserFact, OpinionPair
        from config import LLM_BASE_URL, LLM_API_KEY
        
        try:
            # Call LLM to form opinion
            prompt = render_template(
                "opinion_formation.j2",
                topic=topic,
                user_position=user_position,
            )
            
            headers = {
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": self.llm_model,
                "messages": [
                    {"role": "system", "content": load_prompt("opinion_formation_system.j2")},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 500,
                "temperature": 0.7,
            }
            
            response = await self.http_client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON response
            import json
            try:
                # Try to extract JSON from response
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    result = json.loads(json_str)
                else:
                    result = json.loads(content)
            except json.JSONDecodeError:
                # Use defaults if parsing fails
                result = {
                    "agreement_level": "insufficient_data",
                    "agent_position": "Unable to form a clear position",
                    "agent_reasoning": "Could not parse LLM response",
                    "confidence": 0.3,
                }
            
            now = datetime.now(timezone.utc).isoformat()
            
            # Create opinion pair
            pair = OpinionPair(
                topic=topic,
                user_position=user_position,
                agent_position=result.get("agent_position", ""),
                agent_reasoning=result.get("agent_reasoning", ""),
                agent_confidence=result.get("confidence", 0.5),
                agreement_level=result.get("agreement_level", "partial"),
                created_at=now,
                updated_at=now,
            )
            
            # Store as fact
            fact_id = self.store.add(
                context_id=REFLECTION_CONTEXT_ID,
                content=f"Opinion: {topic}",
                category=FactCategory.OPINION_PAIR,
                source=FactSource.MODEL_OBSERVED,
                confidence=pair.agent_confidence,
                metadata=pair.to_dict(),
            )

            return {
                "topic": topic,
                "user_position": user_position,
                "agent_position": pair.agent_position,
                "agent_reasoning": pair.agent_reasoning,
                "agreement_level": pair.agreement_level,
                "confidence": pair.agent_confidence,
                "fact_id": fact_id,
            }
            
        except Exception as e:
            logger.warning(f"[OpinionFormer] Single opinion formation failed: {e}")
            return None
    
    def _find_opinion_pair(
        self,
        topic: str,
        existing_pairs: List[Any],
    ) -> Any | None:
        """Find an existing opinion pair for a topic.
        
        Args:
            topic: Topic to search for
            existing_pairs: List of existing opinion_pair facts
            
        Returns:
            Existing fact or None
        """
        topic_lower = topic.lower()
        
        for pair in existing_pairs:
            if topic_lower in pair.content.lower():
                return pair
            metadata = pair.metadata or {}
            if topic_lower in metadata.get("topic", "").lower():
                return pair
        
        return None
    
    async def review_opinion_evolution(self) -> List[Dict[str, Any]]:
        """Review existing opinions for potential evolution.
        
        Checks if new evidence or context should update existing opinions.
        
        Returns:
            List of evolved opinions
        """
        from memory.user_facts import FactCategory
        
        evolved = []
        
        try:
            pairs = self.store.list_by_category(REFLECTION_CONTEXT_ID, FactCategory.OPINION_PAIR)

            for pair in pairs:
                metadata = pair.metadata or {}
                evolution = metadata.get("evolution", [])
                
                # If opinion is old (>30 days) and hasn't evolved, consider review
                created = metadata.get("created_at", "")
                if created:
                    try:
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        age_days = (datetime.now(timezone.utc) - created_dt).days
                        
                        if age_days > 30 and len(evolution) == 0:
                            # Mark for potential review
                            evolved.append({
                                "topic": metadata.get("topic", ""),
                                "fact_id": pair.id,
                                "needs_review": True,
                                "reason": "Opinion hasn't been reviewed in30+ days",
                            })
                    except:
                        pass
                        
        except Exception as e:
            logger.warning(f"[OpinionFormer] Evolution review failed: {e}")
        
        return evolved
