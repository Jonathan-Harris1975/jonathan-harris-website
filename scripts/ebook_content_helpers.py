from __future__ import annotations

import re

TOPIC_INTRO_OVERRIDES = {
    "Agriculture": "These titles look at AI in agriculture where weather, margins, labour, and yield all start arguing at once. The useful question is not whether the tech sounds clever, but whether it helps farmers make better calls in the field.",
    "Artificial Intelligence": "These titles deal with artificial intelligence itself: how the systems work, where the claims wobble, and what the technology is genuinely good at. Useful if you want the field explained without the smoke machine.",
    "Construction": "These books cover AI in construction where budgets, delays, safety, and planning collide. They focus on whether the tooling improves delivery in the real world instead of just making the slide deck shinier.",
    "Creativity": "These titles look at AI in creative work without pretending the messy bits have vanished. Expect the tension between speed and originality, plus the awkward rights questions people usually mutter past.",
    "Cyber Security": "These books deal with AI in cyber security where detection, response, and noise all arrive in the same van. The focus stays on practical defence, risk, and what actually changes when automation joins the fight.",
    "Defence": "These titles examine AI in defence with the politics, procurement, and human stakes left firmly on the table. The aim is to understand capability and consequence, not just marvel at the hardware.",
    "Education": "These books look at AI in education where support, assessment, and shortcuts constantly blur together. They ask what helps people learn better and what simply automates the paperwork around learning.",
    "Energy": "These titles cover AI in energy systems where reliability and forecasting matter more than buzzwords. The emphasis is on grids, demand, resilience, and how much control you really want to hand over.",
    "Environment": "These books explore AI in environmental work where monitoring, modelling, and policy are often jammed together. They focus on what the tools can genuinely improve and where the green gloss gets a bit theatrical.",
    "Ethics": "These titles tackle AI and ethics where convenience, fairness, accountability, and public trust keep bumping into each other. Expect fewer slogans and more of the awkward questions people should be asking earlier.",
    "Finance": "These books examine AI in finance where speed, risk, fraud, and regulation never stop circling each other. The point is to understand where automation earns its keep and where it quietly creates new liabilities.",
    "Future of Work": "These titles look at AI and the future of work beyond the usual utopian sales patter. They focus on what changes inside roles, teams, and decision-making once the software stops being a novelty.",
    "Gaming": "These books cover AI in gaming from design and balance to player manipulation and monetisation. They keep one eye on the craft and the other on the business tricks lurking behind the curtain.",
    "Government": "These titles examine AI in government where public service, data handling, and accountability all have to coexist. The focus is on whether the systems improve delivery without turning transparency into collateral damage.",
    "Healthcare": "These books look at AI in healthcare where clinical judgement, workflow pressure, and patient safety meet. The useful question is where the technology genuinely helps care rather than simply adding another dashboard.",
    "History": "These titles treat AI through a historical lens so the current noise has some proper context. They help separate what is genuinely new from the same old promises in a sharper suit.",
    "Industry": "These books cover AI in industry where uptime, quality, cost, and safety all matter at once. They keep the focus on operations and outcomes instead of pretending every factory is one software update away from paradise.",
    "Law": "These titles examine AI in law where precedent, evidence, compliance, and speed make an uneasy quartet. The aim is to understand what the tools can do without forgetting how expensive mistakes become.",
    "Manufacturing": "These books look at AI in manufacturing where efficiency only matters if it survives contact with the plant floor. They focus on maintenance, process control, quality, and the decisions humans still need to own.",
    "Media": "These titles explore AI in media where production speed, trust, and platform incentives rarely point in the same direction. They focus on what happens to judgement, craft, and credibility once the tools start doing more of the work.",
    "Retail": "These books cover AI in retail where forecasting, recommendation engines, and customer experience all compete for attention. The useful bit is understanding where the tech helps the business and where it just gets creepier.",
    "Science": "These titles look at AI in science where modelling, experimentation, and interpretation all need discipline. They focus on where the systems accelerate research and where they still need a human with a decent scepticism filter.",
    "Sports": "These books examine AI in sport where performance analysis, injury prevention, and fan engagement collide. They keep one foot in the numbers and the other in the human judgement that still decides matches.",
    "Transportation": "These titles cover AI in transportation across road, rail, air, and sea. The emphasis is on safety, logistics, reliability, and what happens when optimisation starts steering systems people actually depend on.",
}

RESPONSIVE_IMAGE_WIDTHS = (180, 240, 320, 480, 640, 960, 1280)


def topic_intro(topic: str) -> str:
    topic_name = (topic or "").strip() or "Artificial Intelligence"
    return TOPIC_INTRO_OVERRIDES.get(
        topic_name,
        f"These titles look at AI in {topic_name.lower()} with the hype stripped out and the practical detail left in place. The job is to show what the tools really change, where they help, and where they still need a wary human eye.",
    )


def default_short(topic: str, pages: int | None) -> str:
    prefix = f"A {pages}-page guide" if pages else "A practical guide"
    if (topic or "").strip().lower() == "artificial intelligence":
        return f"{prefix} to artificial intelligence itself, written in plain English with practical examples and grounded analysis."
    return f"{prefix} to AI in {topic.lower()}, written in plain English with practical examples and grounded analysis."


def normalise_topic_copy(value: str, topic: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return cleaned

    substitutions = [
        (r"\bAI in artificial intelligence itself\b", "artificial intelligence itself"),
        (r"\bview of AI in artificial intelligence itself\b", "view of artificial intelligence itself"),
        (r"\bhow AI changes artificial intelligence itself in practice\b", "how artificial intelligence changes in practice"),
        (r"\bwhere AI fits inside artificial intelligence itself\b", "where artificial intelligence fits into the wider field"),
        (r"\bAI is not arriving in artificial intelligence itself\b", "AI is not arriving out of nowhere"),
        (r"\bAI in ai in\s+", "AI in "),
        (r"\bof AI in ai in\s+", "of AI in "),
        (r"\bin ai in\s+", "in "),
        (r"\bdeployment in ai in\s+", "deployment in "),
        (r"\bdo in ai in\s+", "do in "),
        (r"\bAi in gambling\b", "AI in gambling"),
        (r"\bconnect AI with artificial intelligence\b", "cover artificial intelligence directly"),
        (r"\bBest for people weighing real adoption choices in artificial intelligence itself\b", "Best for people weighing real adoption choices across artificial intelligence"),
    ]
    for pattern, replacement in substitutions:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.I)

    if (topic or "").strip().lower() == "artificial intelligence":
        cleaned = re.sub(r"\bAI in artificial intelligence\b", "artificial intelligence", cleaned, flags=re.I)
        cleaned = re.sub(r"\bartificial intelligence itself itself\b", "artificial intelligence itself", cleaned, flags=re.I)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalise_audience_copy(audience: str, topic: str) -> str:
    cleaned = normalise_topic_copy(audience, topic)
    cleaned = re.sub(r"^This [^.]+ title is aimed at ", "", cleaned, flags=re.I)
    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        return cleaned
    return cleaned + "."


def audience_faq_answer(audience: str, topic: str) -> str:
    return normalise_audience_copy(audience, topic)


def build_same_source_srcset(src: str, intrinsic_width: int | None) -> str:
    """Return an empty srcset until the pipeline has real width-specific variants.

    Repeating the same source URL across width descriptors misleads browsers and
    validation tooling into believing responsive candidates exist when they do not.
    The caller should fall back to a plain src-only image in that case.
    """
    return ""


def cover_sizes(class_name: str = "") -> str:
    class_name = class_name or ""
    if "featured" in class_name:
        return "(min-width: 1100px) 180px, (min-width: 768px) 28vw, 50vw"
    return "(min-width: 1200px) 248px, (min-width: 768px) 33vw, 48vw"
