












from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from memory.user_facts import UserFactStore
    from agent.reflection.engine import ReflectionEngine

logger = logging.getLogger(__name__)

class CommandHandler:








    def __init__(
        self,
        store: "UserFactStore",
        reflection_engine: Optional["ReflectionEngine"] = None,
        context_id: str = "",
    ):







        self.store = store
        self.reflection_engine = reflection_engine
        self.context_id = context_id
        
        self._handlers = {
            "/reflect": self._handle_reflect,
            "/gaps": self._handle_gaps,
            "/patterns": self._handle_patterns,
            "/opinions": self._handle_opinions,
            "/growth": self._handle_growth,
            "/meta": self._handle_meta,
            "/tools": self._handle_tools,
        }
    
    def handle(self, command: str, args: str = "") -> str:









        command = command.lower().strip()
        
        handler = self._handlers.get(command)
        if handler:
            try:
                return handler(args)
            except Exception as e:
                logger.error(f"[CommandHandler] Error handling {command}: {e}")
                return f"Error executing {command}: {str(e)}"
        
        return f"Unknown command: {command}. Available: {', '.join(self._handlers.keys())}"
    
    def _handle_reflect(self, args: str) -> str:




        if not self.reflection_engine:
            return "Reflection engine not available."
        
        import asyncio
        
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self.reflection_engine.run_reflection_cycle(reason="on_demand")
            )
            return "Reflection cycle initiated. Check logs for results."
        except RuntimeError:
            try:
                result = asyncio.run(
                    self.reflection_engine.run_reflection_cycle(reason="on_demand")
                )
                return self._format_reflection_result(result)
            except Exception as e:
                return f"Failed to run reflection: {e}"
    
    def _format_reflection_result(self, result: Dict[str, Any]) -> str:

        lines = [
            "# Reflection Cycle Complete",
            "",
            f"**Reason:** {result.get('reason', 'unknown')}",
            f"**Timestamp:** {result.get('timestamp', 'unknown')}",
            "",
            "## Results",
            "",
            f"- **Patterns Detected:** {result.get('patterns_detected', 0)}",
            f"- **Opinions Formed:** {result.get('opinions_formed', 0)}",
            f"- **Gaps Promoted:** {result.get('gaps_promoted', 0)}",
            f"- **Meta Observations:** {result.get('meta_observations', 0)}",
            f"- **Growth Suggestions:** {result.get('growth_suggestions', 0)}",
        ]
        
        if result.get("error"):
            lines.extend(["", f"**Error:** {result['error']}"])
        
        return "\n".join(lines)
    
    def _handle_gaps(self, args: str) -> str:




        from memory.user_facts import FactCategory

        if not self.context_id:
            return "Error: No context ID set for this session."

        min_triggers = 1
        if args.strip().isdigit():
            min_triggers = int(args.strip())

        gaps = self.store.list_capability_gaps(
            context_id=self.context_id,
            min_triggers=min_triggers
        )
        
        if not gaps:
            return f"No capability gaps with at least {min_triggers} trigger(s)."
        
        lines = [
            f"# Capability Gaps ({len(gaps)} total)",
            "",
            "| Priority | Status | Triggers | Description |",
            "|----------|--------|----------|-------------|",
        ]
        
        for gap in gaps[:20]:
            lines.append(
                f"| {gap.priority_score:.2f} | {gap.status} | {gap.trigger_count} | {gap.content[:60]}... |"
            )
        
        if gaps[0].workaround:
            lines.extend([
                "",
                "## Top Gap Workaround",
                f"**{gaps[0].content[:80]}:** {gaps[0].workaround}",
            ])
        
        return "\n".join(lines)
    
    def _handle_patterns(self, args: str) -> str:




        from memory.user_facts import FactCategory

        if not self.context_id:
            return "Error: No context ID set for this session."

        reflections = self.store.list_by_category(
            context_id=self.context_id,
            category=FactCategory.SESSION_REFLECTION
        )
        
        patterns = []
        for ref in reflections:
            metadata = ref.metadata or {}
            if metadata.get("pattern_type"):
                patterns.append({
                    "description": ref.content,
                    "type": metadata.get("pattern_type", "unknown"),
                    "frequency": metadata.get("frequency", 1),
                    "confidence": metadata.get("confidence", 0.5),
                    "trend": metadata.get("trend_direction", "stable"),
                    "actionable": metadata.get("actionable", False),
                    "suggested_action": metadata.get("suggested_action"),
                })
        
        if not patterns:
            return "No patterns detected yet. Run /reflect to detect patterns."
        
        lines = [
            f"# Detected Patterns ({len(patterns)} total)",
            "",
        ]
        
        for p in patterns[:15]:
            emoji = "📈" if p["trend"] == "increasing" else "📉" if p["trend"] == "decreasing" else "➡️"
            action = "✅" if p["actionable"] else ""
            lines.append(f"## {p['type'].title()} Pattern {emoji} {action}")
            lines.append(f"**Description:** {p['description']}")
            lines.append(f"**Frequency:** {p['frequency']} | **Confidence:** {p['confidence']:.0%}")
            if p["suggested_action"]:
                lines.append(f"**Suggested Action:** {p['suggested_action']}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _handle_opinions(self, args: str) -> str:




        from memory.user_facts import FactCategory

        if not self.context_id:
            return "Error: No context ID set for this session."

        pairs = self.store.list_by_category(
            context_id=self.context_id,
            category=FactCategory.OPINION_PAIR
        )
        
        if not pairs:
            return "No opinion pairs logged yet."
        
        lines = [
            f"# Opinion Pairs ({len(pairs)} total)",
            "",
        ]
        
        for pair in pairs[:15]:
            metadata = pair.metadata or {}
            agreement = metadata.get("agreement_level", "partial")
            emoji = "🟢" if agreement == "agree" else "🟡" if agreement == "partial" else "🔴" if agreement == "disagree" else "⚪"
            
            lines.append(f"## {metadata.get('topic', pair.content[:50])} {emoji}")
            lines.append(f"**Operator Position:** {metadata.get('user_position', 'N/A')}")
            lines.append(f"**Agent Position:** {metadata.get('agent_position', 'N/A')}")
            lines.append(f"**Reasoning:** {metadata.get('agent_reasoning', 'N/A')}")
            lines.append(f"**Confidence:** {metadata.get('agent_confidence', 0):.0%}")
            
            evolution = metadata.get("evolution", [])
            if evolution:
                lines.append(f"**Evolution:** {len(evolution)} changes")
            lines.append("")
        
        return "\n".join(lines)
    
    def _handle_growth(self, args: str) -> str:




        from agent.reflection.growth_tracker import GrowthTracker

        if not self.context_id:
            return "Error: No context ID set for this session."

        days = 30
        if args.strip().isdigit():
            days = int(args.strip())

        tracker = GrowthTracker(self.store, self.context_id)
        report = tracker.generate_growth_report(days_back=days)

        return report.get("summary", "No growth report generated.")
    
    def _handle_meta(self, args: str) -> str:




        from agent.reflection.meta_analysis import MetaAnalyzer

        if not self.context_id:
            return "Error: No context ID set for this session."

        analyzer = MetaAnalyzer(self.store)
        return analyzer.get_category_report()
    
    def _handle_tools(self, args: str) -> str:




        from memory.user_facts import FactCategory

        if not self.context_id:
            return "Error: No context ID set for this session."

        suggestions = self.store.list_by_category(
            context_id=self.context_id,
            category=FactCategory.TOOL_SUGGESTION
        )
        
        if not suggestions:
            return "No tool suggestions yet. Capability gaps need 3+ triggers to be promoted."
        
        lines = [
            f"# Tool Suggestions ({len(suggestions)} total)",
            "",
        ]
        
        for suggestion in suggestions:
            metadata = suggestion.metadata or {}
            priority = metadata.get("priority_score", 0)
            triggers = metadata.get("trigger_count", 0)
            criteria = metadata.get("acceptance_criteria", [])
            contexts = metadata.get("example_contexts", [])
            
            lines.append(f"## {suggestion.content}")
            lines.append(f"**Priority:** {priority:.2f} | **Triggers:** {triggers}")
            
            if criteria:
                lines.append("**Acceptance Criteria:**")
                for c in criteria:
                    lines.append(f"- ☐ {c}")
            
            if contexts:
                lines.append("**Example Triggers:**")
                for ctx in contexts[:3]:
                    lines.append(f"- {ctx[:80]}...")
            
            lines.append("")
        
        return "\n".join(lines)

def get_command_handler(
    store: Optional["UserFactStore"] = None,
    reflection_engine: Optional["ReflectionEngine"] = None,
    context_id: str = "",
) -> CommandHandler:










    if store is None:
        from memory.user_facts import get_user_fact_store
        store = get_user_fact_store()

    return CommandHandler(store, reflection_engine, context_id)
