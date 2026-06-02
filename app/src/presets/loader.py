





import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Preset:

    slug: str
    name: str
    description: str
    model: str
    
    def to_dict(self) -> Dict[str, str]:

        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
        }

STATIC_PRESETS = [
    Preset(
        slug="architecture",
        name="Architecture",
        description=(
            "System design, architecture planning, and infrastructure design at the "
            "conceptual and strategic level. Includes: debugging strategies, error handling "
            "patterns, resilience patterns, FinOps and cost optimization, capacity planning, "
            "SRE platform design, SLO/SLI/SLA planning, AI/ML infrastructure planning, "
            "platform engineering, backend design, software design, roadmap planning, "
            "technical RFC review, ADR writing, architecture critique and evaluation. "
            "Also includes high-level technology choices, comparing frameworks or tools, "
            "scaling strategies, migration planning, and trade-off analysis between approaches. "
            "These are complex discussions requiring senior-level reflection. "
            "The output is plans, diagrams, trade-off analysis, or professional evaluations. "
            "If the expected output is actual code, configuration files, or IaC modules "
            "being written or modified, prefer code instead. "
            "If the topic is primarily about security posture, threat modeling, or "
            "compliance, prefer security instead."
        ),
        model="@preset/architecture"
    ),
    Preset(
        slug="code",
        name="Code",
        description=(
            "Writing, reading, modifying, reviewing, debugging, or explaining code and "
            "configuration files. Includes: application code in any language, Terraform "
            "modules, Kubernetes manifests, Helm charts, Dockerfiles, CI/CD pipeline "
            "definitions (GitHub Actions, GitLab CI, ArgoCD configs), monitoring configs "
            "(Prometheus rules, Grafana dashboards), AI/ML training scripts, data processing "
            "pipelines, automation scripts, backend code, API development, tests, and any "
            "task where the expected output is a concrete code or config artifact being "
            "created or modified. Also includes code review, explaining what specific code "
            "does, and debugging specific errors. "
            "If the discussion is about high-level system design, technology choices, or "
            "trade-off analysis without producing code, prefer architecture instead. "
            "If the request would result in a one-liner command or very short shell "
            "script, prefer shell instead."
        ),
        model="@preset/code"
    ),
    Preset(
        slug="shell",
        name="Shell",
        description=(
            "One-liner commands, piped commands, short shell scripts, CLI usage, and "
            "terminal troubleshooting. Includes: kubectl, helm, terraform CLI, docker CLI, "
            "git, argocd, aws cli, az cli, gcloud, prometheus, openssl, curl, httpie, ssh, "
            "scp, dig, traceroute, top, htop, strace, netstat, ss, jq, yq, awk, sed, grep, "
            "environment variable configuration, PATH troubleshooting, file permissions, "
            "and process management. Questions are typically how-to's, flag/option lookups, "
            "or quick command composition. "
            "If the request requires a full script with logic, loops, error handling, or "
            "structured code beyond a short snippet, prefer code instead."
        ),
        model="@preset/shell"
    ),
    Preset(
        slug="security",
        name="Security",
        description=(
            "Security-focused discussions: threat modeling, vulnerability assessment, "
            "penetration testing methodology, security architecture review, compliance "
            "frameworks (SOC2, ISO 27001, PCI-DSS, HIPAA), IAM design, network security, "
            "zero-trust architecture, secrets management, encryption strategies, CVE "
            "analysis, incident response planning, security hardening, OWASP guidance, "
            "WAF and DDoS mitigation, supply chain security, container security, "
            "cloud security posture (AWS, Azure, GCP), and security tool evaluation. "
            "The primary concern is attack surface, risk, and defensive posture. "
            "If the task is writing security-related code (OPA policies, network policies, "
            "security scanning configs), prefer code. If the task is running security tools "
            "from the command line, prefer shell. Security is for the analysis, strategy, "
            "and evaluation layer."
        ),
        model="@preset/security"
    ),
    Preset(
        slug="health",
        name="Health",
        description=(
            "Physical health, fitness, nutrition, and sports performance. Includes: diets, "
            "meal planning, macros, supplements, powerlifting, bodybuilding, workout "
            "programming, recovery, sleep, mobility, deload strategies, injury management, "
            "powerlifting competition preparation, peaking, water cutting, weight management, "
            "body composition, bloodwork interpretation, symptoms, medications, medical "
            "conditions, and general physical wellness. "
            "Does not include emotional distress, psychological struggles, existential "
            "concerns, or mental health support — those belong in mental_health. "
            "Does not include healthcare costs, insurance, or medical billing — those "
            "belong in general or finance."
        ),
        model="@preset/health"
    ),
    Preset(
        slug="mental_health",
        name="Mental Health",
        description=(
            "A safe space for emotional processing, venting, and mental health support. "
            "Includes: expressions of hopelessness, despair, frustration with life, "
            "existential dread, burnout, grief, loneliness, anxiety, depression, "
            "self-worth struggles, feeling overwhelmed, relationship distress, identity "
            "crises, and any signal — explicit or between the lines — that the operator "
            "is in genuine emotional pain. Also covers: coping strategies, stress "
            "management, grounding techniques, and guiding toward professional resources. "
            "This is a black box — the operator may vent without seeking solutions. "
            "The priority is acknowledgment and presence, not problem-solving. "
            "If the topic is clinical (medication questions, diagnosis criteria, "
            "symptoms of a specific disorder), prefer health. Mental health is for "
            "the human experience of struggling, not the clinical framing of it."
        ),
        model="@preset/mental_health"
    ),
    Preset(
        slug="finance",
        name="Finance",
        description=(
            "Financial instrument knowledge, market data, and structured financial "
            "analysis. Includes: ETFs, stocks, crypto, investment accounts, bonds, "
            "options, investing, trading, technical analysis, risk management, taxes, "
            "retirement, FIRE, saving, budgeting, debt management, investing strategies, "
            "financial planning, financial independence, financial education, financial "
            "analysis, financial reporting, financial statements, financial ratios, "
            "financial metrics, financial modeling, financial forecasting, portfolio "
            "strategy, and market commentary. "
            "Excludes any scenario where the core question is about a relationship, "
            "personal judgment, interpersonal conflict, or behavior that merely involves "
            "money as context — e.g. lending money to a friend, someone spending "
            "irresponsibly, back pay disputes, whether to cut someone off financially. "
            "Those belong in general."
        ),
        model="@preset/finance"
    ),
    Preset(
        slug="proofreader",
        name="Proofreader",
        description=(
            "Proofreading, editing, and rewriting non-code text. Includes: emails, "
            "messages, Slack drafts, cover letters, professional correspondence, essays, "
            "documentation prose, social media posts, bios, announcements, apologies, "
            "complaints, and any text where the operator wants grammar correction, tone "
            "adjustment, clarity improvement, or a full rewrite. "
            "The operator may provide text and ask for a polished version, or ask for "
            "help drafting something from scratch with specific tone requirements. "
            "If the text being edited is code, documentation comments, or README files "
            "within a code project, prefer code instead."
        ),
        model="@preset/proofreader"
    ),
    Preset(
        slug="social",
        name="Social",
        description=(
            'Greetings, farewells, onomatopoeia, emotional one-word responses, casual '
            'chat, compliments, insults, small talk, reactions, acknowledgments, '
            'expressions, internet slang, meme speak, jokes, banter, "thanks", "got it", '
            '"lol", "nice". Social interactions where there is no substantive information '
            "request and no emotional distress. Pure social exchange. "
            "If the message contains any actual question or task embedded in casual "
            "framing, prefer the category that matches that task over social. "
            "If the operator is expressing genuine emotional pain or distress even "
            "casually, prefer mental_health."
        ),
        model="@preset/social"
    ),
    Preset(
        slug="general",
        name="General",
        description=(
            "General knowledge, personal decisions, moral guidance, career advice, "
            "creative writing, brainstorming, philosophical questions, opinions on "
            "what to learn, relationship advice, interpersonal conflicts, workplace "
            "dynamics, life decisions, and anything that does not fit a more specific "
            "category. Also catches personal situations where money, numbers, or "
            "technical terms appear as context but the real question is about judgment, "
            "values, or behavior — e.g. should I lend money to a friend, my coworker "
            "got promoted and acts differently, someone spent their back pay irresponsibly. "
            "This is the catch-all. If a message genuinely fits no other preset, it "
            "belongs here. Always non-technical."
        ),
        model="@preset/general"
    ),
    Preset(
        slug="pondering",
        name="Pondering",
        description=(
            "Agent-initiated reflective conversation. Focus on learning "
            "about the operator — goals, preferences, context, plans. "
            "Not for technical problem-solving."
        ),
        model="@preset/pondering"
    ),
]

class PresetManager:







    
    def __init__(self):
        self.presets: Dict[str, Preset] = {}
        self._initialized = False
    
    def load_presets(self) -> None:







        if not STATIC_PRESETS:
            raise RuntimeError(
                "No presets defined. Add at least one preset to STATIC_PRESETS."
            )
        
        for preset in STATIC_PRESETS:
            self.presets[preset.slug] = preset
            logger.info(f"Loaded preset: {preset.slug} - {preset.description[:50]}...")
        
        if not self.presets:
            raise RuntimeError(
                "No valid presets loaded. Check STATIC_PRESETS configuration."
            )
        
        self._initialized = True
        logger.info(f"Successfully loaded {len(self.presets)} preset(s)")
    
    def get_preset(self, slug: str) -> Optional[Preset]:








        return self.presets.get(slug)
    
    def get_all_presets(self) -> Dict[str, Preset]:





        return self.presets.copy()
    
    def get_preset_descriptions(self) -> Dict[str, str]:







        return {
            slug: preset.description
            for slug, preset in self.presets.items()
        }
    
    def is_initialized(self) -> bool:

        return self._initialized
    
    def slugs(self) -> List[str]:







        return list(self.presets.keys())

_preset_manager: Optional[PresetManager] = None

def get_preset_manager() -> PresetManager:





    global _preset_manager
    if _preset_manager is None:
        _preset_manager = PresetManager()
    return _preset_manager
