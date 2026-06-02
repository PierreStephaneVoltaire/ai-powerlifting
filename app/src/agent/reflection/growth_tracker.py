









from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Any, List, Dict
from collections import defaultdict

from config import REFLECTION_CONTEXT_ID

if TYPE_CHECKING:
    from memory.user_facts import UserFactStore

logger = logging.getLogger(__name__)

class GrowthTracker:










    
    def __init__(self, store: "UserFactStore"):





        self.store = store
    
    def generate_growth_report(self, days_back: int = 30) -> Dict[str, Any]:








        report = {
            "period_days": days_back,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "knowledge_gaps": [],
            "skills_trending_up": [],
            "abandoned_interests": [],
            "suggestions": [],
            "summary": "",
        }
        
        try:
            report["knowledge_gaps"] = self._analyze_knowledge_gaps(days_back)
            
            report["skills_trending_up"] = self._analyze_skill_progression(days_back)
            
            report["abandoned_interests"] = self._find_abandoned_interests(days_back)
            
            report["suggestions"] = self._generate_suggestions(report)
            
            report["summary"] = self._generate_summary(report)
            
            logger.info(f"[GrowthTracker] Generated growth report for {days_back} days")
            
        except Exception as e:
            logger.error(f"[GrowthTracker] Report generation failed: {e}")
        
        return report
    
    def _analyze_knowledge_gaps(self, days_back: int) -> List[Dict[str, Any]]:










        from memory.user_facts import FactCategory
        
        gaps = []
        
        try:
            misconceptions = self.store.list_by_category(REFLECTION_CONTEXT_ID, FactCategory.MISCONCEPTION)

            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
            recent = []
            
            for misc in misconceptions:
                last_seen = misc.metadata.get("last_seen", misc.created_at)
                if last_seen:
                    try:
                        dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                        if dt > cutoff:
                            recent.append(misc)
                    except:
                        pass
            
            by_domain: Dict[str, List[Any]] = defaultdict(list)
            for misc in recent:
                domain = misc.metadata.get("domain", "general")
                by_domain[domain].append(misc)
            
            for domain, miscs in by_domain.items():
                total_occurrences = sum(
                    m.metadata.get("recurrence_count", 1) for m in miscs
                )
                
                recent_count = 0
                older_count = 0
                week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                
                for m in miscs:
                    last_seen = m.metadata.get("last_seen", "")
                    if last_seen:
                        try:
                            dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                            if dt > week_ago:
                                recent_count += 1
                            else:
                                older_count += 1
                        except:
                            pass
                
                if recent_count > older_count:
                    trend = "increasing"
                elif recent_count < older_count:
                    trend = "decreasing"
                else:
                    trend = "stable"
                
                resources = []
                for m in miscs:
                    resources.extend(m.metadata.get("suggested_resources", []))
                resources = list(set(resources))[:3]
                
                gaps.append({
                    "domain": domain,
                    "misconception_count": len(miscs),
                    "total_occurrences": total_occurrences,
                    "trend": trend,
                    "examples": [
                        {
                            "what_they_said": m.metadata.get("what_they_said", ""),
                            "what_is_correct": m.metadata.get("what_is_correct", ""),
                        }
                        for m in miscs[:3]
                    ],
                    "suggested_resources": resources,
                })
            
            gaps.sort(key=lambda x: x["total_occurrences"], reverse=True)
            
        except Exception as e:
            logger.warning(f"[GrowthTracker] Knowledge gap analysis failed: {e}")
        
        return gaps
    
    def _analyze_skill_progression(self, days_back: int) -> List[Dict[str, Any]]:











        from memory.user_facts import FactCategory
        
        trending = []
        
        try:
            ctx = REFLECTION_CONTEXT_ID
            skills = self.store.list_by_category(ctx, FactCategory.SKILL)
            topics = self.store.list_by_category(ctx, FactCategory.TOPIC_LOG)
            
            all_facts = skills + topics
            
            by_topic: Dict[str, List[Any]] = defaultdict(list)
            
            for fact in all_facts:
                content = fact.content.lower()
                
                topic = self._extract_topic(content)
                if topic:
                    by_topic[topic].append(fact)
            
            for topic, facts in by_topic.items():
                if len(facts) < 2:
                    continue
                
                sorted_facts = sorted(
                    [f for f in facts if f.created_at],
                    key=lambda f: f.created_at
                )
                
                if len(sorted_facts) < 2:
                    continue
                
                early_facts = sorted_facts[:len(sorted_facts)//2]
                late_facts = sorted_facts[len(sorted_facts)//2:]
                
                early_avg_len = sum(len(f.content) for f in early_facts) / len(early_facts)
                late_avg_len = sum(len(f.content) for f in late_facts) / len(late_facts)
                
                if late_avg_len > early_avg_len * 1.2:
                    trending.append({
                        "topic": topic,
                        "engagement_count": len(facts),
                        "progression_indicator": "increasing_complexity",
                        "first_seen": sorted_facts[0].created_at,
                        "last_seen": sorted_facts[-1].created_at,
                    })
            
            trending.sort(key=lambda x: x["engagement_count"], reverse=True)
            
        except Exception as e:
            logger.warning(f"[GrowthTracker] Skill progression analysis failed: {e}")
        
        return trending
    
    def _find_abandoned_interests(self, days_back: int) -> List[Dict[str, Any]]:











        from memory.user_facts import FactCategory
        
        abandoned = []
        
        try:
            ctx = REFLECTION_CONTEXT_ID
            topics = self.store.list_by_category(ctx, FactCategory.TOPIC_LOG)
            interests = self.store.list_by_category(ctx, FactCategory.INTEREST_AREA)
            
            all_facts = topics + interests
            
            now = datetime.now(timezone.utc)
            recent_cutoff = now - timedelta(days=30)
            older_cutoff = now - timedelta(days=60)
            
            by_topic: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"recent": 0, "older": 0, "last_seen": None})
            
            for fact in all_facts:
                if not fact.created_at:
                    continue
                    
                try:
                    dt = datetime.fromisoformat(fact.created_at.replace("Z", "+00:00"))
                    topic = self._extract_topic(fact.content.lower())
                    
                    if topic:
                        if dt > recent_cutoff:
                            by_topic[topic]["recent"] += 1
                        elif dt > older_cutoff:
                            by_topic[topic]["older"] += 1
                        
                        if by_topic[topic]["last_seen"] is None or dt > by_topic[topic]["last_seen"]:
                            by_topic[topic]["last_seen"] = dt
                            
                except:
                    pass
            
            for topic, counts in by_topic.items():
                if counts["older"] >= 2 and counts["recent"] == 0:
                    abandoned.append({
                        "topic": topic,
                        "previous_engagement": counts["older"],
                        "last_seen": counts["last_seen"].isoformat() if counts["last_seen"] else None,
                        "abandoned_days": (now - counts["last_seen"]).days if counts["last_seen"] else None,
                    })
            
            abandoned.sort(key=lambda x: x["previous_engagement"], reverse=True)
            
        except Exception as e:
            logger.warning(f"[GrowthTracker] Abandoned interests analysis failed: {e}")
        
        return abandoned
    
    def _extract_topic(self, content: str) -> str | None:










        tech_keywords = [
            "python", "javascript", "typescript", "rust", "golang", "go",
            "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
            "react", "vue", "angular", "node", "django", "flask",
            "sql", "postgres", "mysql", "mongodb", "redis",
            "graphql", "rest", "api", "microservices",
            "machine learning", "ai", "llm", "gpt", "neural",
            "networking", "security", "devops", "ci/cd",
            "testing", "tdd", "agile", "scrum",
        ]
        
        content_lower = content.lower()
        
        for keyword in tech_keywords:
            if keyword in content_lower:
                return keyword
        
        return None
    
    def _generate_suggestions(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:








        suggestions = []
        
        for gap in report.get("knowledge_gaps", []):
            if gap["trend"] == "increasing":
                suggestions.append({
                    "type": "learning",
                    "priority": "high",
                    "domain": gap["domain"],
                    "suggestion": f"Consider focused learning on {gap['domain']} - "
                                 f"{gap['misconception_count']} misconceptions detected",
                    "resources": gap.get("suggested_resources", []),
                })
        
        for skill in report.get("skills_trending_up", []):
            suggestions.append({
                "type": "advancement",
                "priority": "medium",
                "domain": skill["topic"],
                "suggestion": f"Ready for advanced {skill['topic']} topics - "
                             "engagement is progressing well",
                "resources": [],
            })
        
        for interest in report.get("abandoned_interests", []):
            suggestions.append({
                "type": "re-engagement",
                "priority": "low",
                "domain": interest["topic"],
                "suggestion": f"Consider revisiting {interest['topic']} - "
                             f"no activity for {interest.get('abandoned_days', '?')} days",
                "resources": [],
            })
        
        return suggestions
    
    def _generate_summary(self, report: Dict[str, Any]) -> str:








        lines = [
            f"## Operator Growth Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "",
            f"Analysis period: {report['period_days']} days",
            "",
        ]
        
        gaps = report.get("knowledge_gaps", [])
        if gaps:
            lines.append("### Knowledge Gaps Identified")
            for gap in gaps[:3]:
                trend_emoji = "📈" if gap["trend"] == "increasing" else "📉" if gap["trend"] == "decreasing" else "➡️"
                lines.append(f"- **{gap['domain']}** — {gap['misconception_count']} misconceptions {trend_emoji}")
                if gap.get("suggested_resources"):
                    lines.append(f"  - Suggested: {', '.join(gap['suggested_resources'][:2])}")
            lines.append("")
        
        trending = report.get("skills_trending_up", [])
        if trending:
            lines.append("### Skills Trending Up")
            for skill in trending[:3]:
                lines.append(f"- **{skill['topic']}** ({skill['engagement_count']} engagements)")
            lines.append("")
        
        abandoned = report.get("abandoned_interests", [])
        if abandoned:
            lines.append("### Abandoned Interests")
            for interest in abandoned[:3]:
                lines.append(f"- **{interest['topic']}** (last: {interest.get('abandoned_days', '?')} days ago)")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_misconception_report(self) -> str:





        from memory.user_facts import FactCategory
        
        lines = ["# Misconception Report", ""]
        
        try:
            misconceptions = self.store.list_by_category(REFLECTION_CONTEXT_ID, FactCategory.MISCONCEPTION)

            by_domain: Dict[str, List[Any]] = defaultdict(list)
            for misc in misconceptions:
                domain = misc.metadata.get("domain", "general")
                by_domain[domain].append(misc)
            
            for domain, miscs in sorted(by_domain.items()):
                lines.append(f"## {domain.title()}")
                lines.append("")
                
                for misc in miscs:
                    lines.append(f"### {misc.metadata.get('topic', 'Unknown')}")
                    lines.append(f"- **What they said:** {misc.metadata.get('what_they_said', 'N/A')}")
                    lines.append(f"- **Correct:** {misc.metadata.get('what_is_correct', 'N/A')}")
                    lines.append(f"- **Severity:** {misc.metadata.get('severity', 'minor')}")
                    lines.append(f"- **Recurrence:** {misc.metadata.get('recurrence_count', 1)}")
                    
                    resources = misc.metadata.get("suggested_resources", [])
                    if resources:
                        lines.append(f"- **Resources:** {', '.join(resources)}")
                    lines.append("")
                    
        except Exception as e:
            lines.append(f"Error generating report: {e}")
        
        return "\n".join(lines)
