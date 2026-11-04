"""
MIND Universal Studio — Conversational Design Consultant & Structured Design Brief Engine.

Acts as an intelligent pre-Stitch design consultant that:
1. Detects ambiguous website design requests and identifies missing architectural/visual requirements.
2. Presents contextual domain archetypes (e.g., K–12 Academy, University, Elementary School,
   Language Academy, Coding/Technical School, Other) with clear explanations of design direction
   and intended audience.
3. Asks adaptive follow-up questions ONLY for material design dimensions that the user has not
   already answered (audience, purpose: informational vs. portal, required pages, key features,
   visual direction & branding).
4. Accumulates requirements across multiple conversational turns while isolating separate design sessions.
5. Synthesizes a 10-part `StructuredDesignBrief` and converts it into a rich Google Stitch prompt
   and revision context.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ArchetypeOption:
    """Represents a selectable subtype option with design direction and audience explanation."""

    key: str
    label: str
    design_direction: str
    intended_audience: str
    default_purpose: str
    default_pages: List[str]
    default_sections: List[str]
    default_visual_direction: str
    default_branding: str
    default_special_functionality: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "design_direction": self.design_direction,
            "intended_audience": self.intended_audience,
            "default_purpose": self.default_purpose,
            "default_pages": list(self.default_pages),
            "default_sections": list(self.default_sections),
            "default_visual_direction": self.default_visual_direction,
            "default_branding": self.default_branding,
            "default_special_functionality": list(self.default_special_functionality),
        }


@dataclass
class StructuredDesignBrief:
    """
    Comprehensive 10-part design brief synthesized from conversational discovery
    and used as the authoritative input to Google Stitch.
    """

    project_type: str
    target_audience: str
    website_purpose: str
    required_pages_and_screens: List[str]
    navigation_structure: str
    important_content_sections: List[str]
    visual_direction: str
    branding_requirements: str
    responsive_requirements: str
    special_functionality: List[str]
    title: str = "Website Design"
    domain_category: str = "general"
    subtype: str = ""
    session_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "domain_category": self.domain_category,
            "subtype": self.subtype,
            "session_id": self.session_id,
            "project_type": self.project_type,
            "target_audience": self.target_audience,
            "website_purpose": self.website_purpose,
            "required_pages_and_screens": list(self.required_pages_and_screens),
            "navigation_structure": self.navigation_structure,
            "important_content_sections": list(self.important_content_sections),
            "visual_direction": self.visual_direction,
            "branding_requirements": self.branding_requirements,
            "responsive_requirements": self.responsive_requirements,
            "special_functionality": list(self.special_functionality),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredDesignBrief":
        return cls(
            title=str(data.get("title", "Website Design")),
            domain_category=str(data.get("domain_category", "general")),
            subtype=str(data.get("subtype", "")),
            session_id=str(data.get("session_id", "")),
            project_type=str(data.get("project_type", "Website")),
            target_audience=str(data.get("target_audience", "General audience")),
            website_purpose=str(data.get("website_purpose", "Informational website")),
            required_pages_and_screens=list(data.get("required_pages_and_screens") or ["Home"]),
            navigation_structure=str(data.get("navigation_structure", "Top navigation bar with CTA")),
            important_content_sections=list(data.get("important_content_sections") or []),
            visual_direction=str(data.get("visual_direction", "Modern responsive interface")),
            branding_requirements=str(data.get("branding_requirements", "Consistent brand identity")),
            responsive_requirements=str(data.get("responsive_requirements", "Desktop, tablet, and mobile responsive")),
            special_functionality=list(data.get("special_functionality") or []),
            created_at=float(data.get("created_at", time.time())),
        )

    def format_for_user(self) -> str:
        """Formats the 10-field structured design brief for presentation in MIND Chat."""
        pages_str = ", ".join(self.required_pages_and_screens)
        sections_str = "; ".join(self.important_content_sections)
        func_str = ", ".join(self.special_functionality)
        return (
            f"### 📋 Structured Design Brief — {self.title}\n"
            f"- **Project Type:** {self.project_type}\n"
            f"- **Target Audience:** {self.target_audience}\n"
            f"- **Website Purpose:** {self.website_purpose}\n"
            f"- **Required Pages & Screens:** {pages_str}\n"
            f"- **Navigation Structure:** {self.navigation_structure}\n"
            f"- **Important Content Sections:** {sections_str}\n"
            f"- **Visual Direction:** {self.visual_direction}\n"
            f"- **Branding Requirements:** {self.branding_requirements}\n"
            f"- **Responsive Requirements:** {self.responsive_requirements}\n"
            f"- **Special Functionality:** {func_str}"
        )

    def to_stitch_prompt(self) -> str:
        """
        Constructs a focused, high-signal prompt for Google Stitch `generate_screen_from_text`
        that preserves all 10 brief dimensions while avoiding multi-screen generation timeouts.
        """
        pages_str = ", ".join(self.required_pages_and_screens[:6])
        sections_str = "; ".join(s[:90] for s in self.important_content_sections[:4])
        func_str = ", ".join(self.special_functionality[:4])
        return (
            f"Design a flagship desktop website screen for '{self.title}' ({self.project_type}).\n"
            f"1. Target Audience: {self.target_audience}.\n"
            f"2. Website Purpose: {self.website_purpose}.\n"
            f"3. Required Pages & Screens: {pages_str}.\n"
            f"4. Navigation Structure: Top navbar with [{pages_str}] and primary CTA.\n"
            f"5. Key Content Sections: {sections_str}.\n"
            f"6. Visual Direction: {self.visual_direction}.\n"
            f"7. Branding Requirements: {self.branding_requirements}.\n"
            f"8. Responsive Requirements: {self.responsive_requirements}.\n"
            f"9. Special Functionality: {func_str}."
        )

    def to_stitch_revision_prompt(self, revision_request: str) -> str:
        """Enriches a user revision request with the active design brief context."""
        return (
            f"Apply the following design revision to the '{self.title}' ({self.project_type}) website: "
            f"{revision_request.strip()}.\n"
            f"Preserve the established context — Audience: {self.target_audience}; "
            f"Purpose: {self.website_purpose}; Visual Direction: {self.visual_direction}; "
            f"Required Pages: {', '.join(self.required_pages_and_screens)}."
        )


# ─── Domain Archetype Definitions ───────────────────────────────────────────

SCHOOL_ARCHETYPES: List[ArchetypeOption] = [
    ArchetypeOption(
        key="k12",
        label="K–12 Academy / Private School",
        design_direction="Structured academic excellence, admissions pathways, division spotlights (Lower, Middle, Upper School), and vibrant campus life.",
        intended_audience="Prospective parents, current families, and K–12 students.",
        default_purpose="Informational & admissions website showcasing academic rigor, campus community, and enrollment steps",
        default_pages=["Home", "About & Mission", "Academics", "Admissions & Tuition", "Campus Life & Athletics", "Contact"],
        default_sections=[
            "Hero banner with campus photography, mission headline, and 'Inquire / Schedule a Tour' CTAs",
            "Academic divisions overview (Lower, Middle, and Upper School pathways)",
            "Signature programs & innovation spotlight (STEM labs, arts, athletics)",
            "Admissions timeline, tuition & financial aid overview",
            "Student life metrics, parent testimonials, and upcoming campus events",
        ],
        default_visual_direction="Modern prestigious academic aesthetic with deep navy, warm gold accents, crisp daylight backgrounds, and editorial typography",
        default_branding="Academy crest badge in header, authoritative serif headings paired with clean sans-serif body text, and accreditation highlights",
        default_special_functionality=[
            "Interactive admissions checklist & tour booking CTA",
            "Division curriculum switcher (Lower / Middle / Upper)",
            "Campus events & athletics calendar preview",
        ],
    ),
    ArchetypeOption(
        key="university",
        label="University / Higher Education",
        design_direction="Comprehensive multi-faculty research and degree exploration portal with campus news, global rankings, and department navigation.",
        intended_audience="Prospective undergraduate & graduate students, faculty researchers, and alumni.",
        default_purpose="Institutional higher-education website for degree discovery, admissions, and research showcase",
        default_pages=["Home", "Admissions", "Academics & Degrees", "Research & Innovation", "Campus Life", "Alumni & Giving"],
        default_sections=[
            "Cinematic hero with degree finder search bar and application deadlines",
            "Undergraduate & graduate program explorer by faculty",
            "Research breakthroughs and global impact metrics",
            "Campus virtual tour, housing, and student organizations",
        ],
        default_visual_direction="Bold editorial university layout with rich scholarly crimson/slate palette, high-impact photography, and structured grid",
        default_branding="University seal, prominent degree search header, and research impact counters",
        default_special_functionality=[
            "Interactive degree & major finder",
            "Admissions deadline tracker",
            "Faculty & research spotlight cards",
        ],
    ),
    ArchetypeOption(
        key="elementary",
        label="Elementary School",
        design_direction="Warm, welcoming, safety-first community hub with playful color accents, classroom highlights, and easy parent access.",
        intended_audience="Parents of young children, elementary students, and local families.",
        default_purpose="Family-friendly informational school website and parent resource hub",
        default_pages=["Home", "Our School", "Classrooms & Curriculum", "Parent Resources", "Lunch & Calendar", "Enrollment"],
        default_sections=[
            "Friendly welcoming hero with principal's greeting and quick parent links",
            "Early childhood & grade-level learning highlights",
            "Weekly school calendar, lunch menu, and safety procedures",
            "PTA announcements and family gallery",
        ],
        default_visual_direction="Warm, bright, approachable daylight design with sky blue, sunshine yellow, and soft rounded cards",
        default_branding="Friendly school mascot/emblem, high-readability rounded typography, and clear parent quick-links",
        default_special_functionality=[
            "Parent quick-links bar (Calendar, Lunch Menu, Attendance)",
            "Grade-level curriculum cards",
            "New family enrollment guide",
        ],
    ),
    ArchetypeOption(
        key="language",
        label="Language Academy",
        design_direction="Dynamic, culturally immersive course and proficiency-level showcase with flexible schedules and direct online enrollment.",
        intended_audience="Adult learners, international students, professionals, and language enthusiasts.",
        default_purpose="Course catalog, proficiency assessment, and student enrollment website",
        default_pages=["Home", "Languages & Courses", "CEFR Levels", "Class Schedule", "Cultural Immersion", "Enroll Now"],
        default_sections=[
            "Hero with language selector, placement test CTA, and upcoming cohort dates",
            "Interactive course tracks (Beginner A1 to Advanced C2, Business, Intensive)",
            "Native instructor profiles and immersive cultural events",
            "Tuition packages and student video testimonials",
        ],
        default_visual_direction="Vibrant, contemporary international aesthetic with teal, coral, and clean card-based course comparison",
        default_branding="Multilingual badge accents, CEFR level progression graphics, and trust reviews",
        default_special_functionality=[
            "Language & proficiency level filter",
            "Free placement test call-to-action",
            "Cohort schedule & tuition comparison table",
        ],
    ),
    ArchetypeOption(
        key="coding",
        label="Coding or Technical School",
        design_direction="High-contrast modern tech aesthetic emphasizing intensive bootcamps, hands-on project portfolios, and career placement outcomes.",
        intended_audience="Career switchers, aspiring software engineers, data scientists, and tech upskillers.",
        default_purpose="Career accelerator and technical bootcamp admissions platform",
        default_pages=["Home", "Bootcamp Tracks", "Curriculum & Projects", "Career Outcomes", "Tuition & Financing", "Apply"],
        default_sections=[
            "High-impact tech hero with hiring partner logos, salary uplift stats, and 'Apply Now' CTA",
            "Program tracks (Full-Stack Engineering, AI & Machine Learning, Cybersecurity, Cloud)",
            "Week-by-week syllabus breakdown and capstone project showcase",
            "Career coaching, hiring outcomes, and flexible financing options",
        ],
        default_visual_direction="Sleek dark-mode developer studio aesthetic with electric cyan, emerald accents, monospace code badges, and bento-grid metrics",
        default_branding="Tech academy wordmark, verified graduate outcome counters, and employer partner strip",
        default_special_functionality=[
            "Interactive bootcamp track selector",
            "Syllabus module accordion",
            "Tuition & ISA financing calculator preview",
        ],
    ),
    ArchetypeOption(
        key="other",
        label="Other",
        design_direction="Custom educational institution, Montessori program, arts conservatory, or specialized training center tailored to your description.",
        intended_audience="Custom student, parent, or professional learner community.",
        default_purpose="Custom educational showcase and enrollment website",
        default_pages=["Home", "About", "Programs", "Admissions", "Community", "Contact"],
        default_sections=[
            "Custom institutional hero with primary call-to-action",
            "Program and curriculum overview",
            "Admissions and community highlights",
        ],
        default_visual_direction="Clean, modern responsive educational interface tailored to institutional identity",
        default_branding="Custom institutional emblem, cohesive color system, and clear typographic hierarchy",
        default_special_functionality=[
            "Program inquiry form",
            "Interactive curriculum overview",
        ],
    ),
]


RESTAURANT_ARCHETYPES: List[ArchetypeOption] = [
    ArchetypeOption(
        key="fine_dining",
        label="Fine Dining / Chef's Table",
        design_direction="Atmospheric, editorial luxury layout emphasizing tasting menus, sommelier pairings, and table reservations.",
        intended_audience="Discerning diners, food enthusiasts, and special-occasion guests.",
        default_purpose="Tasting menu showcase and online table reservation experience",
        default_pages=["Home", "Tasting Menu", "Wine Cellar", "Our Chef", "Private Dining", "Reservations"],
        default_sections=["Atmospheric hero with reservation widget", "Seasonal tasting menu", "Chef philosophy & culinary story"],
        default_visual_direction="Moody obsidian and warm champagne gold palette with editorial serif typography",
        default_branding="Minimalist monogram crest and full-bleed culinary photography",
        default_special_functionality=["Interactive table reservation selector", "Dietary & wine pairing toggle"],
    ),
    ArchetypeOption(
        key="cafe_bistro",
        label="Artisan Cafe / Bakery & Bistro",
        design_direction="Warm, inviting neighborhood showcase featuring daily pastries, specialty coffee, and online pickup ordering.",
        intended_audience="Local commuters, remote workers, and weekend brunch guests.",
        default_purpose="Menu showcase, store hours/location finder, and online pickup ordering",
        default_pages=["Home", "Coffee & Menu", "Seasonal Bakery", "Our Story", "Order Pickup", "Visit Us"],
        default_sections=["Warm hero with daily roast & order CTA", "Categorized coffee & pastry menu", "Location map & hours"],
        default_visual_direction="Warm espresso brown, oat cream, and terracotta accents with friendly craft typography",
        default_branding="Artisan stamp logo and warm natural textures",
        default_special_functionality=["Interactive menu category filter", "Quick online pickup order bar"],
    ),
    ArchetypeOption(
        key="fast_casual",
        label="Modern Fast-Casual / Street Food",
        design_direction="High-energy, bold visual layout built around customizable bowls/items, nutrition badges, and rapid online ordering.",
        intended_audience="Busy professionals, students, and delivery/takeout customers.",
        default_purpose="Direct online ordering, menu customization, and loyalty rewards",
        default_pages=["Home", "Order Online", "Build Your Own", "Nutrition", "Locations", "Rewards"],
        default_sections=["Vibrant food hero with 'Order Now' CTA", "Interactive meal builder preview", "Loyalty club banner"],
        default_visual_direction="High-contrast vibrant lime/chili palette with bold geometric display type",
        default_branding="Bold street-food badge and high-saturation dish photography",
        default_special_functionality=["Interactive meal customizer", "Store locator & pickup timer"],
    ),
]


DOMAIN_ARCHETYPES_MAP: Dict[str, List[ArchetypeOption]] = {
    "school": SCHOOL_ARCHETYPES,
    "restaurant": RESTAURANT_ARCHETYPES,
}


class ConversationalDesignConsultant:
    """
    Stateful design discovery consultant that evaluates website requests,
    asks adaptive clarification questions only for missing material dimensions,
    and produces a `StructuredDesignBrief` for Google Stitch.
    """

    # Broad domain triggers that have distinct sub-archetypes
    BROAD_DOMAIN_PATTERNS: Dict[str, str] = {
        "school": r"\b(school|academy|university|college|education|educational|elementary|kindergarten|k-12|k12|campus|bootcamp|institute)\b",
        "restaurant": r"\b(restaurant|cafe|bistro|diner|eatery|dining|steakhouse|pizzeria)\b",
        "healthcare": r"\b(clinic|hospital|medical|healthcare|dental|dentist|doctor|telemedicine)\b",
        "ecommerce": r"\b(e-commerce|ecommerce|online\s+store|webstore|marketplace|shop)\b",
        "fitness": r"\b(gym|fitness|yoga|pilates|crossfit|workout\s+studio)\b",
        "portfolio": r"\b(portfolio|personal\s+website|creative\s+agency)\b",
    }

    @classmethod
    def infer_domain_category(cls, text: str) -> str:
        lower = text.lower()
        for domain, pattern in cls.BROAD_DOMAIN_PATTERNS.items():
            if re.search(pattern, lower):
                return domain
        return "general"

    @classmethod
    def get_archetypes_for_domain(cls, domain: str) -> List[ArchetypeOption]:
        if domain in DOMAIN_ARCHETYPES_MAP:
            return DOMAIN_ARCHETYPES_MAP[domain]
        # Generic archetypes for other broad domains
        return [
            ArchetypeOption(
                key="informational_brand",
                label="Brand & Marketing Showcase",
                design_direction="Story-driven landing experience highlighting value proposition, services, and trust signals.",
                intended_audience="Prospective clients, customers, and general visitors.",
                default_purpose="Brand positioning, service discovery, and lead generation",
                default_pages=["Home", "About", "Services", "Case Studies", "Pricing", "Contact"],
                default_sections=["Hero with primary value proposition & CTA", "Core services grid", "Testimonials & trust metrics", "Contact & inquiry section"],
                default_visual_direction="Modern high-contrast editorial layout with refined brand accents",
                default_branding="Clean brand wordmark, consistent iconography, and social proof badges",
                default_special_functionality=["Interactive service filter", "Lead capture & scheduling CTA"],
            ),
            ArchetypeOption(
                key="interactive_portal",
                label="Customer / Member Web Portal",
                design_direction="Utility-focused application layout featuring dashboards, account actions, and structured workflows.",
                intended_audience="Registered users, members, and active customers.",
                default_purpose="Self-service portal, bookings, and interactive user workflows",
                default_pages=["Dashboard", "Directory / Catalog", "Bookings & Schedule", "Resources", "Account Settings"],
                default_sections=["Quick-action dashboard header", "Interactive status & schedule cards", "Searchable resource directory"],
                default_visual_direction="Clean product UI with structured sidebar/top navigation and data cards",
                default_branding="Compact product header, status pills, and accessible component system",
                default_special_functionality=["Search & filter toolbar", "Interactive booking / status widget"],
            ),
            ArchetypeOption(
                key="other",
                label="Other",
                design_direction="Custom layout and architecture tailored to your specific project goals.",
                intended_audience="Custom target audience defined by your requirements.",
                default_purpose="Custom web experience",
                default_pages=["Home", "Overview", "Features", "About", "Contact"],
                default_sections=["Hero showcase", "Feature highlights", "Call to action"],
                default_visual_direction="Modern responsive design",
                default_branding="Cohesive custom branding",
                default_special_functionality=["Interactive call-to-action"],
            ),
        ]

    @classmethod
    def create_initial_state(cls, initial_prompt: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates a fresh, isolated discovery state for a new design session."""
        domain = cls.infer_domain_category(initial_prompt)
        sid = session_id or f"disc_{domain}_{int(time.time() * 1000)}"
        state: Dict[str, Any] = {
            "session_id": sid,
            "domain_category": domain,
            "initial_prompt": initial_prompt.strip(),
            "raw_turns": [initial_prompt.strip()],
            "subtype_key": None,
            "subtype_label": None,
            "target_audience": None,
            "website_purpose": None,
            "required_pages": [],
            "main_features": [],
            "visual_direction": None,
            "visual_tone_hint": None,
            "branding_requirements": None,
            "special_functionality": [],
            "stage": "initial",
            "questions_asked": [],
            "timestamp": time.time(),
        }
        cls.extract_and_merge_requirements(initial_prompt, state, is_initial_turn=True)
        return state

    @classmethod
    def is_new_unrelated_design_request(cls, utterance: str, active_state: Dict[str, Any]) -> bool:
        """
        Detects if the user has abandoned the current discovery session to start a
        completely different website design (ensuring session isolation).
        """
        lower = utterance.strip().lower()
        m = re.match(
            r"^(?:design|create|build|make|generate)\s+(?:a\s+|an\s+|the\s+)?(.+?)\s+(?:website|site|web\s+app|landing\s+page|portal)\b",
            lower,
        )
        if not m:
            return False
        new_domain = cls.infer_domain_category(utterance)
        old_domain = active_state.get("domain_category", "general")
        if new_domain != old_domain and new_domain != "general":
            return True
        return False

    @classmethod
    def should_start_discovery(cls, user_command: str) -> bool:
        """
        Determines whether an initial website request is ambiguous and requires
        conversational design discovery before calling Google Stitch.
        """
        raw = user_command.strip()
        lower = raw.lower()

        # If the prompt is already a synthesized StructuredDesignBrief, never re-trigger discovery
        if "structured design brief" in lower or ("1. target audience:" in lower and "3. required pages" in lower):
            return False

        domain = cls.infer_domain_category(raw)
        probe_state: Dict[str, Any] = {
            "domain_category": domain,
            "subtype_key": None,
            "subtype_label": None,
            "target_audience": None,
            "website_purpose": None,
            "required_pages": [],
            "main_features": [],
            "visual_direction": None,
            "visual_tone_hint": None,
            "branding_requirements": None,
            "special_functionality": [],
        }
        cls.extract_and_merge_requirements(raw, probe_state, is_initial_turn=True)

        # Count how many material design dimensions are already explicitly specified
        specified_count = sum([
            bool(probe_state["subtype_label"]),
            bool(probe_state["target_audience"]),
            bool(probe_state["website_purpose"]),
            bool(probe_state["required_pages"]),
            bool(probe_state["main_features"]),
            bool(probe_state["visual_direction"]),
        ])

        # Broad domain requests (e.g. "Design a modern school website", "Create a school website",
        # "Design a restaurant website") or explicit "design ..." prompts that lack critical
        # dimensions must go through Conversational Design Discovery.
        if domain != "general" and specified_count < 4:
            return True

        if lower.startswith("design ") and specified_count < 4:
            return True

        return False

    @classmethod
    def extract_and_merge_requirements(
        cls,
        utterance: str,
        state: Dict[str, Any],
        is_initial_turn: bool = False,
        expected_slot: Optional[str] = None,
    ) -> None:
        """
        Extracts subtype, audience, purpose, pages, features, and visual style from
        `utterance` and merges them into `state` without overwriting already-established facts
        unless refined by the user.
        """
        text = utterance.strip()
        lower = text.lower()
        domain = state.get("domain_category", "general")
        archetypes = cls.get_archetypes_for_domain(domain)

        # 1. Subtype extraction
        explicit_other = bool(re.match(r"^(?:6\b|option\s*6\b|other\b)", lower))
        if explicit_other:
            custom_clean = re.sub(r"^(?:6\.?|option\s*6\.?|other)\s*[:\-–]?\s*", "", text, flags=re.IGNORECASE).strip()
            # Take the first clause as the custom subtype label
            first_clause = re.split(r"[,.;]|\b(?:targeting|for\s+auditioning|with\s+pages|featuring)\b", custom_clean, maxsplit=1)[0].strip()
            first_clause = re.sub(r"^(?:it's\s+a|it\s+is\s+a|a|an)\s+", "", first_clause, flags=re.IGNORECASE).strip()
            state["subtype_key"] = "other"
            state["subtype_label"] = f"Other — {first_clause[:70].title()}" if first_clause else "Other (Custom Direction)"
        elif domain == "school":
            if re.search(r"\b(k-12|k–12|k12|private\s+school|prep\s+school|high\s+school|secondary\s+school|k\s+to\s+12)\b", lower):
                cls._apply_archetype(state, archetypes[0])
            elif re.search(r"\b(university|higher\s+education|college|undergraduate|graduate\s+school)\b", lower):
                cls._apply_archetype(state, archetypes[1])
            elif re.search(r"\b(elementary|primary\s+school|grade\s+school|kindergarten)\b", lower):
                cls._apply_archetype(state, archetypes[2])
            elif re.search(r"\b(language\s+academy|language\s+school|esl|foreign\s+language)\b", lower):
                cls._apply_archetype(state, archetypes[3])
            elif re.search(r"\b(coding|technical\s+school|bootcamp|stem\s+academy|vocational|tech\s+school)\b", lower):
                cls._apply_archetype(state, archetypes[4])
        elif domain == "restaurant":
            if re.search(r"\b(fine\s+dining|tasting\s+menu|chef|sommelier|steakhouse)\b", lower):
                cls._apply_archetype(state, archetypes[0])
            elif re.search(r"\b(cafe|bistro|bakery|coffee|brunch)\b", lower):
                cls._apply_archetype(state, archetypes[1])
            elif re.search(r"\b(fast\s+casual|street\s+food|takeout|quick\s+service)\b", lower):
                cls._apply_archetype(state, archetypes[2])

        # Check numeric option selection or direct label match when answering subtype slot
        if not state.get("subtype_label") and expected_slot == "design_discovery_subtype":
            for idx, opt in enumerate(archetypes, start=1):
                if (
                    lower == str(idx)
                    or lower.startswith(f"{idx}.")
                    or lower.startswith(f"option {idx}")
                    or opt.key.lower() in lower
                    or opt.label.lower() in lower
                ):
                    cls._apply_archetype(state, opt)
                    break
            # If user described a custom subtype ("other" or freeform description)
            if not state.get("subtype_label") and len(text) >= 2:
                custom_clean = re.sub(r"^other\s*[:\-–]?\s*", "", text, flags=re.IGNORECASE).strip()
                state["subtype_key"] = "custom"
                state["subtype_label"] = custom_clean[:80] if custom_clean else "Custom Institution"

        # 2. Target Audience extraction
        aud_patterns = [
            r"\b(?:audience\s+is|targeting|aimed\s+at|designed\s+for|catering\s+to|website\s+for|site\s+for|portal\s+for)\s+([a-zA-Z0-9,\-\s&/]+?)(?:\.|;|\band\s+(?:include|pages|use|style|highlight|feature)\b|\bwith\s+(?:home|pages|sections)\b|$)",
        ]
        for pat in aud_patterns:
            m_aud = re.search(pat, text, flags=re.IGNORECASE)
            if m_aud:
                cand = m_aud.group(1).strip(" ,.;:")
                # Avoid capturing generic institution/project nouns like "a school", "a modern school website", "university"
                if cand and not re.search(
                    r"\b(website|site|page|design|school|university|academy|college|restaurant|cafe|company|startup|business)\b",
                    cand.lower(),
                ):
                    state["target_audience"] = cand
                    break

        if not state.get("target_audience"):
            aud_keywords = []
            for kw, label in [
                ("prospective parents", "prospective parents"),
                ("parents", "parents and families"),
                ("students", "students"),
                ("prospective families", "prospective families"),
                ("alumni", "alumni"),
                ("faculty", "faculty and staff"),
                ("teachers", "teachers"),
                ("international students", "international students"),
                ("career switchers", "career switchers"),
                ("adult learners", "adult learners"),
            ]:
                if kw in lower and label not in aud_keywords:
                    aud_keywords.append(label)
            if aud_keywords:
                state["target_audience"] = ", ".join(aud_keywords).capitalize()

        # 3. Website Purpose extraction (informational/admissions vs student/parent portal)
        if re.search(
            r"\b(informational|brochure|marketing\s+site|showcase\s+website|public\s+website|admissions\s+website|enrollment\s+website|not\s+a\s+portal)\b",
            lower,
        ):
            if re.search(r"\b(portal|dashboard|login)\b", lower) and not re.search(r"\bnot\s+a\s+portal\b", lower):
                state["website_purpose"] = "Hybrid informational & admissions website with student/parent portal access"
            else:
                state["website_purpose"] = "Informational & admissions showcase website"
        elif re.search(r"\b(student\s+portal|parent\s+portal|student-facing\s+portal|portal\s+login|interactive\s+portal|dashboard|lms)\b", lower):
            state["website_purpose"] = "Student & parent interactive portal"

        # 4. Required Pages extraction
        known_page_map = [
            (r"\bhome(?:\s+page)?\b", "Home"),
            (r"\babout(?:\s+us)?\b", "About & Mission"),
            (r"\bacademics?\b|\bcurriculum\b|\bcourses?\b|\bprograms?\b", "Academics & Curriculum"),
            (r"\badmissions?\b|\benrollment\b|\bapply\b|\btuition\b", "Admissions & Tuition"),
            (r"\bcampus\s+life\b|\bstudent\s+life\b|\bactivities\b", "Campus Life"),
            (r"\bathletics?\b|\bsports?\b", "Athletics"),
            (r"\barts?\b|\bmusic\b|\btheater\b", "Arts & Culture"),
            (r"\bfaculty\b|\bstaff\b|\bdirectory\b", "Faculty Directory"),
            (r"\bevents?\b|\bcalendar\b|\bnews\b", "News & Events Calendar"),
            (r"\bparent\s+portal\b|\bstudent\s+portal\b|\bportal\b", "Parent & Student Portal"),
            (r"\bcontact(?:\s+us)?\b|\bvisit\b", "Contact & Visit"),
            (r"\bmenu\b", "Menu"),
            (r"\breservations?\b|\bbooking\b", "Reservations"),
            (r"\bpricing\b|\bplans\b", "Pricing"),
            (r"\bservices\b", "Services"),
            (r"\bportfolio\b|\bprojects\b", "Portfolio"),
        ]
        extracted_pages: List[str] = list(state.get("required_pages") or [])
        for pat, page_title in known_page_map:
            if re.search(pat, lower) and page_title not in extracted_pages:
                extracted_pages.append(page_title)
        if extracted_pages:
            if "Home" not in extracted_pages:
                extracted_pages.insert(0, "Home")
            state["required_pages"] = extracted_pages

        # 5. Main Features & Special Functionality extraction
        feature_Catalog = [
            (r"\bstem\b|\brobotics\b|\blabs?\b|\binnovation\b", "STEM & Robotics Innovation Labs"),
            (r"\bathletics?\b|\bsports\s+teams?\b|\bstadium\b", "Championship Athletics & Sports Programs"),
            (r"\barts?\b|\bperforming\s+arts\b|\bstudio\b", "Visual & Performing Arts Conservatory"),
            (r"\bscholarships?\b|\bfinancial\s+aid\b|\btuition\b", "Tuition & Scholarship Calculator / Financial Aid Guide"),
            (r"\bvirtual\s+tour\b|\bcampus\s+tour\b|\bschedule\s+a\s+tour\b", "Interactive Campus Tour Booking"),
            (r"\bcalendar\b|\bevents?\b", "Interactive Academic & Events Calendar"),
            (r"\badmissions?\s+(?:tracker|process|steps|inquiry|form)\b|\bonline\s+application\b", "Step-by-Step Admissions & Application Portal"),
            (r"\btestimonials?\b|\balumni\s+stories\b|\boutcomes?\b|\bcollege\s+counseling\b", "Graduate Outcomes & Family Testimonials"),
            (r"\bclubs?\b|\bextracurricular\b|\ boarding\b", "Student Clubs & Extracurricular Directory"),
            (r"\blibrary\b|\bresearch\b", "Digital Library & Research Commons"),
        ]
        features: List[str] = list(state.get("main_features") or [])
        for pat, feat_label in feature_Catalog:
            if re.search(pat, lower) and feat_label not in features:
                features.append(feat_label)

        # Also extract freeform features after "highlight", "features:", "focus on", "showcase"
        m_feat = re.search(
            r"(?:highlight(?:ing)?|featur(?:e|es|ing)|showcase|focus\s+on|emphasize)\s+([a-zA-Z0-9,\-\s&]+?)(?:\.|;|\busing\b|\bwith\s+a\b|\bstyle\b|$)",
            text,
            flags=re.IGNORECASE,
        )
        if m_feat:
            raw_feat = m_feat.group(1).strip(" ,.;:")
            if raw_feat and len(raw_feat) > 3 and raw_feat not in features:
                features.append(raw_feat)

        if features:
            state["main_features"] = features

        # 6. Visual Direction & Color Palette extraction
        style_keywords = [
            "navy", "gold", "crimson", "emerald", "royal blue", "slate", "pastel", "warm",
            "minimalist", "prestigious", "heritage", "classic", "editorial", "playful",
            "vibrant", "dark mode", "light mode", "daylight", "glassmorphism", "cyberpunk",
            "clean", "luxury", "earthy", "monochrome", "teal", "coral",
        ]
        matched_styles = [kw for kw in style_keywords if kw in lower]
        if matched_styles:
            # Capture full style phrase if present
            m_style = re.search(
                r"(?:visual\s+style|style|palette|theme|colors?|look|aesthetic|using\s+a)\s*[:\-]?\s*([a-zA-Z0-9,\-\s&#]+?)(?:\.|;|$)",
                text,
                flags=re.IGNORECASE,
            )
            if m_style and len(m_style.group(1).strip()) > 3:
                state["visual_direction"] = m_style.group(1).strip(" ,.;:")
            else:
                tone_prefix = f"{state.get('visual_tone_hint')} " if state.get("visual_tone_hint") else ""
                state["visual_direction"] = f"{tone_prefix}{', '.join(matched_styles)} aesthetic".strip().capitalize()
        elif "modern" in lower and is_initial_turn:
            state["visual_tone_hint"] = "modern"
        elif not is_initial_turn and expected_slot == "design_discovery_details" and any(w in lower for w in ["modern", "clean", "sleek", "bright", "professional"]):
            state["visual_direction"] = "Modern, clean high-contrast academic interface"

    @staticmethod
    def _apply_archetype(state: Dict[str, Any], option: ArchetypeOption) -> None:
        state["subtype_key"] = option.key
        state["subtype_label"] = option.label

    @classmethod
    def get_next_clarification(cls, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determines whether additional clarification is needed before synthesizing the
        `StructuredDesignBrief`. Returns `None` once sufficient requirements are gathered.
        """
        domain = state.get("domain_category", "general")
        archetypes = cls.get_archetypes_for_domain(domain)
        questions_asked: List[str] = state.get("questions_asked") or []

        # Check if user explicitly asked to skip further questions and generate right away
        last_turn = (state.get("raw_turns") or [""])[-1].lower()
        if len(state.get("raw_turns") or []) > 1 and any(
            p in last_turn for p in ["just generate", "skip questions", "you decide", "use defaults", "go ahead and design"]
        ):
            return None

        # ─── STAGE 1: Contextual Subtype Clarification ──────────────────────
        if not state.get("subtype_label") and "design_discovery_subtype" not in questions_asked:
            questions_asked.append("design_discovery_subtype")
            state["questions_asked"] = questions_asked
            state["stage"] = "awaiting_subtype"

            domain_noun = "school" if domain == "school" else (domain if domain != "general" else "website")
            lines = [
                f"To design the right **{domain_noun} website**, different institution types need distinct layouts, navigation, and tone.",
                "",
                "Which type of institution are we designing for? *(Select an option below or describe a different direction)*:",
                "",
            ]
            option_labels: List[str] = []
            for idx, opt in enumerate(archetypes, start=1):
                lines.append(
                    f"{idx}. **{opt.label}** — *{opt.design_direction}* (**Audience:** {opt.intended_audience})"
                )
                option_labels.append(opt.label)

            question_text = "\n".join(lines)
            return {
                "slot_name": "design_discovery_subtype",
                "stage": "DESIGN_DISCOVERY_SUBTYPE",
                "question": question_text,
                "options": option_labels,
                "archetypes": [a.to_dict() for a in archetypes],
                "explanation": f"Requesting {domain_noun} archetype selection before generating design brief.",
            }

        # ─── STAGE 2: Adaptive Follow-up for Missing Material Dimensions ────
        missing_questions: List[Tuple[str, str]] = []

        if not state.get("target_audience"):
            if domain == "school":
                missing_questions.append((
                    "target_audience",
                    "**Primary Audience:** Who is the primary audience to prioritize (e.g., prospective parents & families, current students, or alumni)?",
                ))
            else:
                missing_questions.append((
                    "target_audience",
                    "**Primary Audience:** Who is the primary target audience for this website?",
                ))

        if not state.get("website_purpose"):
            if domain == "school":
                missing_questions.append((
                    "website_purpose",
                    "**Website Purpose:** Is this primarily an **informational & admissions website** or a **student/parent-facing portal**?",
                ))
            else:
                missing_questions.append((
                    "website_purpose",
                    "**Website Purpose:** Is this primarily an **informational/marketing website** or an **interactive user portal/store**?",
                ))

        if not state.get("required_pages"):
            if domain == "school":
                missing_questions.append((
                    "required_pages",
                    "**Required Pages:** Which pages are needed (e.g., Home, Academics, Admissions, Campus Life, Athletics, Contact)?",
                ))
            else:
                missing_questions.append((
                    "required_pages",
                    "**Required Pages:** Which core pages or screens should be included?",
                ))

        if not state.get("main_features"):
            if domain == "school":
                missing_questions.append((
                    "main_features",
                    "**Main Features & Highlights:** What signature programs or features should stand out (e.g., STEM/robotics labs, arts, athletics, campus tour booking, scholarships)?",
                ))
            else:
                missing_questions.append((
                    "main_features",
                    "**Main Features:** What key features, services, or interactive elements should be highlighted?",
                ))

        if not state.get("visual_direction"):
            tone_note = " (building on your modern direction)" if state.get("visual_tone_hint") == "modern" else ""
            if domain == "school":
                missing_questions.append((
                    "visual_direction",
                    f"**Visual Style & Branding:** What color palette and visual mood should it use{tone_note} (e.g., prestigious navy & gold, bright minimalist daylight, warm community tones)?",
                ))
            else:
                missing_questions.append((
                    "visual_direction",
                    f"**Visual Style & Branding:** What color palette and visual direction do you prefer{tone_note}?",
                ))

        # Ask the adaptive follow-up questions if we haven't asked Stage 2 yet and at least one material dimension is missing
        if missing_questions and "design_discovery_details" not in questions_asked:
            questions_asked.append("design_discovery_details")
            state["questions_asked"] = questions_asked
            state["stage"] = "awaiting_details"

            subtype_title = state.get("subtype_label") or "Website"
            already_noted: List[str] = [f"Type: **{subtype_title}**"]
            if state.get("target_audience"):
                already_noted.append(f"Audience: **{state['target_audience']}**")
            if state.get("website_purpose"):
                already_noted.append(f"Purpose: **{state['website_purpose']}**")
            if state.get("required_pages"):
                already_noted.append(f"Pages: **{', '.join(state['required_pages'])}**")
            if state.get("main_features"):
                already_noted.append(f"Features: **{', '.join(state['main_features'])}**")
            if state.get("visual_direction"):
                already_noted.append(f"Style: **{state['visual_direction']}**")

            header = (
                f"Got it — we'll design for **{subtype_title}** ({' · '.join(already_noted)}).\n\n"
                "Before I prepare the Structured Design Brief and send it to Google Stitch, "
                "please share a few details on the remaining design decisions:"
            )
            bullets = "\n".join(f"- {q_text}" for _key, q_text in missing_questions)
            question_text = f"{header}\n\n{bullets}"

            return {
                "slot_name": "design_discovery_details",
                "stage": "DESIGN_DISCOVERY_DETAILS",
                "question": question_text,
                "missing_dimensions": [k for k, _ in missing_questions],
                "options": [],
                "explanation": f"Asking {len(missing_questions)} remaining adaptive design question(s) for {subtype_title}.",
            }

        return None

    @classmethod
    def build_structured_brief(
        cls,
        state: Dict[str, Any],
        fallback_title: Optional[str] = None,
    ) -> StructuredDesignBrief:
        """
        Synthesizes the complete 10-part `StructuredDesignBrief` from accumulated
        conversational state and archetype defaults.
        """
        domain = state.get("domain_category", "general")
        archetypes = cls.get_archetypes_for_domain(domain)
        chosen_opt = archetypes[0]
        for opt in archetypes:
            if opt.key == state.get("subtype_key") or opt.label == state.get("subtype_label"):
                chosen_opt = opt
                break

        subtype_label = state.get("subtype_label") or chosen_opt.label
        title = fallback_title or f"{subtype_label} Website"
        if title.lower() in ("modern school website", "school website", "website project") and subtype_label:
            title = f"{subtype_label} — Official Website"

        project_type = f"Website — {subtype_label}" if subtype_label else f"Website ({domain.title()})"
        target_audience = state.get("target_audience") or chosen_opt.intended_audience
        website_purpose = state.get("website_purpose") or chosen_opt.default_purpose
        pages = list(state.get("required_pages") or chosen_opt.default_pages)

        # Build navigation structure from required pages
        primary_nav = " | ".join(pages[:6])
        cta_label = "Inquire / Apply Now" if domain == "school" else "Get Started"
        if "portal" in website_purpose.lower():
            cta_label = "Portal Login / Apply"
        navigation_structure = (
            f"Sticky top navigation bar featuring [{primary_nav}] with a prominent '{cta_label}' "
            "action button, breadcrumb support on inner views, and a structured multi-column institutional footer."
        )

        # Important content sections combining archetype sections + user's main features
        sections = list(chosen_opt.default_sections)
        user_features = state.get("main_features") or []
        for feat in user_features:
            feat_section = f"Dedicated spotlight section: {feat}"
            if not any(feat.lower() in s.lower() for s in sections):
                sections.insert(min(2, len(sections)), feat_section)

        # Visual direction
        visual_dir = state.get("visual_direction") or chosen_opt.default_visual_direction
        if state.get("visual_tone_hint") == "modern" and "modern" not in visual_dir.lower():
            visual_dir = f"Modern {visual_dir[0].lower() + visual_dir[1:]}"

        branding = state.get("branding_requirements") or chosen_opt.default_branding
        responsive = (
            "Desktop-first widescreen (1440px) layout with fluid responsive breakpoints for "
            "tablet (768px) and mobile (390px), accessible touch targets, and collapsible mobile navigation."
        )

        special_func = list(chosen_opt.default_special_functionality)
        for feat in user_features:
            if not any(feat.lower() in sf.lower() for sf in special_func):
                special_func.append(f"Interactive {feat} showcase")

        return StructuredDesignBrief(
            title=title,
            domain_category=domain,
            subtype=subtype_label,
            session_id=str(state.get("session_id") or f"stitch_{domain}"),
            project_type=project_type,
            target_audience=target_audience,
            website_purpose=website_purpose,
            required_pages_and_screens=pages,
            navigation_structure=navigation_structure,
            important_content_sections=sections,
            visual_direction=visual_dir,
            branding_requirements=branding,
            responsive_requirements=responsive,
            special_functionality=special_func,
        )
