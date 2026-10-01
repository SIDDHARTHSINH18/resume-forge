"""Deterministic structured extraction from resume plain text.

Rules-based and evidence-first: every extracted field keeps its source line so
the UI can show *where* information came from. Nothing is inferred beyond
explicit text; unknown values stay None and are displayed as "Not found".

Protected/sensitive characteristics are never inferred. Date of birth is only
captured for display when explicitly written, and is never used in scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import skills_lexicon
from .util import normalize_email, normalize_phone

# --------------------------------------------------------------------------
# data shapes
# --------------------------------------------------------------------------


@dataclass
class EducationItem:
    degree: str | None = None
    course: str | None = None
    institution: str | None = None
    graduation_year: str | None = None
    academic_value: float | None = None
    academic_type: str | None = None  # cgpa | percentage
    raw_line: str = ""


@dataclass
class SkillItem:
    skill: str
    category: str = "general"
    strength: str = "listed"  # strong | moderate | listed
    sources: list[str] = field(default_factory=list)


@dataclass
class ExperienceItem:
    title: str | None = None
    organization: str | None = None
    kind: str = "internship"  # internship | employment
    start_date: str | None = None
    end_date: str | None = None
    duration_months: int | None = None
    description: str = ""
    raw_text: str = ""


@dataclass
class ProjectItem:
    name: str | None = None
    technologies: list[str] = field(default_factory=list)
    description: str = ""
    raw_text: str = ""


@dataclass
class CertificationItem:
    name: str = ""
    issuer: str | None = None
    year: str | None = None


@dataclass
class ExtractedResume:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = field(default_factory=list)
    dob_text: str | None = None
    education: list[EducationItem] = field(default_factory=list)
    skills: list[SkillItem] = field(default_factory=list)
    experience: list[ExperienceItem] = field(default_factory=list)
    projects: list[ProjectItem] = field(default_factory=list)
    certifications: list[CertificationItem] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)
    sections_found: list[str] = field(default_factory=list)

    def best_academic(self) -> tuple[float, str] | None:
        """Highest academic value found (only explicit values are used)."""
        best: tuple[float, str] | None = None
        best_cmp = -1.0
        for item in self.education:
            if item.academic_value is None or not item.academic_type:
                continue
            value = item.academic_value
            comparables = {
                "percentage": value / 9.5,  # 10-point scale, comparison only
                "cgpa": value,
            }
            comparable = comparables.get(item.academic_type, value)
            if comparable > best_cmp:
                best = (value, item.academic_type)
                best_cmp = comparable
        return best


# --------------------------------------------------------------------------
# sectioning
# --------------------------------------------------------------------------

SECTION_KEYWORDS: dict[str, str] = {
    # canonical section -> keywords
    "summary": "summary objective professional summary career objective profile about me about career summary",
    "education": "education educational qualifications academic qualifications academics academic background qualification qualifications education details scholastics academic details",
    "skills": "skills technical skills key skills core competencies competencies areas of expertise technical proficiency skill set it skills computer skills technical expertise programming skills technologies technical knowledge",
    "experience": "experience work experience professional experience employment employment history work history internship internships internship experience industrial training professional background",
    "projects": "projects academic projects personal projects major projects project work key projects academic project mini projects",
    "certifications": "certifications certificates certification courses training trainings courses certifications workshops licenses achievements and certifications",
    "achievements": "achievements awards honors honours awards achievements extracurricular extracurricular activities activities positions of responsibility leadership publications co curricular activities co-curricular activities extra curricular activities volunteering social work",
    "contact": "contact contact details contact information personal details personal information personal profile",
    "other": "languages known hobbies interests declaration references strengths weaknesses",
}

_KEYWORD_TO_SECTION: dict[str, str] = {}
for section, keywords in SECTION_KEYWORDS.items():
    for keyword in keywords.split():
        _KEYWORD_TO_SECTION[keyword] = section

# multi-word headings checked as whole-line matches first
_MULTI_WORD_HEADINGS = {
    "professional summary": "summary",
    "career objective": "summary",
    "about me": "summary",
    "educational qualifications": "education",
    "academic qualifications": "education",
    "academic background": "education",
    "education details": "education",
    "academic details": "education",
    "technical skills": "skills",
    "key skills": "skills",
    "core competencies": "skills",
    "areas of expertise": "skills",
    "technical proficiency": "skills",
    "skill set": "skills",
    "it skills": "skills",
    "computer skills": "skills",
    "technical expertise": "skills",
    "programming skills": "skills",
    "technical knowledge": "skills",
    "work experience": "experience",
    "professional experience": "experience",
    "employment history": "experience",
    "work history": "experience",
    "internship experience": "experience",
    "industrial training": "experience",
    "professional background": "experience",
    "academic projects": "projects",
    "personal projects": "projects",
    "major projects": "projects",
    "project work": "projects",
    "key projects": "projects",
    "academic project": "projects",
    "mini projects": "projects",
    "courses & certifications": "certifications",
    "courses and certifications": "certifications",
    "positions of responsibility": "achievements",
    "extra curricular activities": "achievements",
    "co-curricular activities": "achievements",
    "co curricular activities": "achievements",
    "extracurricular activities": "achievements",
    "languages known": "other",
    "personal details": "contact",
    "personal information": "contact",
    "contact details": "contact",
    "contact information": "contact",
}


def _heading_section(line: str) -> tuple[str, str] | None:
    """If the line is a section heading, return (section, inline_remainder)."""
    stripped = line.strip().strip("•-–—▪| ").strip()
    if not stripped or len(stripped) > 60:
        return None
    if "@" in stripped or re.search(r"\d{2,}", stripped):
        return None
    inline = ""
    heading = stripped
    if ":" in stripped:
        head, rest = stripped.split(":", 1)
        heading, inline = head.strip(), rest.strip()
    lowered = re.sub(r"[\s&]+", " ", heading.lower().replace("&", " ")).strip(" .:-")
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"^(my|the)\s+", "", lowered)
    if lowered in _MULTI_WORD_HEADINGS:
        return _MULTI_WORD_HEADINGS[lowered], inline
    tokens = [tok for tok in lowered.split() if tok != "and"]
    if 1 <= len(tokens) <= 3 and all(tok in _KEYWORD_TO_SECTION for tok in tokens):
        return _KEYWORD_TO_SECTION[tokens[0]], inline
    if len(tokens) == 1 and tokens[0] in _KEYWORD_TO_SECTION:
        return _KEYWORD_TO_SECTION[tokens[0]], inline
    return None


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"_header": []}
    current = "_header"
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        heading = _heading_section(line)
        if heading:
            section, inline = heading
            current = section
            sections.setdefault(current, [])
            if inline:
                sections[current].append(inline)
            continue
        sections.setdefault(current, []).append(line)
    return sections


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_LABEL_RE = re.compile(r"(?:phone|mobile|contact|cell|tel)\b[:\s]*([+()\-\s\d]{8,20})", re.IGNORECASE)
PHONE_GENERIC_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,6}")
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s,;)]+|(?<![\w@.-])[a-z0-9-]+\.(?:com|dev|io|me|net|in|org)(?:/[^\s,;)]*)?",
    re.IGNORECASE,
)
DOB_RE = re.compile(
    r"(?:date\s+of\s+birth|d\.?o\.?b\.?|born)\s*[:\-]?\s*([0-9]{1,2}[\s./-][A-Za-z0-9]{2,9}[\s./-][0-9]{2,4})",
    re.IGNORECASE,
)
NAME_LABEL_RE = re.compile(r"^(?:name|candidate name)\s*[:\-]\s*(.+)$", re.IGNORECASE)
NAME_BLOCKLIST = {
    "resume", "curriculum vitae", "cv", "bio data", "biodata", "profile", "summary",
    "objective", "contact", "personal details", "personal information", "declaration",
    "references", "achievements", "education", "skills", "experience", "projects",
}
NAME_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*){1,3}$")

KNOWN_CITIES = {
    "ahmedabad", "mumbai", "bombay", "pune", "delhi", "new delhi", "noida", "gurgaon",
    "gurugram", "bangalore", "bengaluru", "hyderabad", "chennai", "madras", "kolkata",
    "calcutta", "surat", "vadodara", "baroda", "rajkot", "jaipur", "lucknow", "kanpur",
    "indore", "bhopal", "nagpur", "nashik", "thane", "coimbatore", "kochi", "cochin",
    "trivandrum", "thiruvananthapuram", "chandigarh", "mohali", "amritsar", "ludhiana",
    "dehradun", "jodhpur", "udaipur", "guwahati", "patna", "ranchi", "bhubaneswar",
    "visakhapatnam", "vijayawada", "mysore", "mysuru", "mangalore", "mangaluru",
    "hubli", "belgaum", "aurangabad", "kolhapur", "gandhinagar", "anand", "bhavnagar",
    "jamnagar", "junagadh", "navsari", "vapi", "valsad", "mehsana", "palanpur",
    "bhubaneshwar", "cuttack", "rourkela", "siliguri", "durgapur", "howrah", "agra",
    "varanasi", "allahabad", "prayagraj", "meerut", "ghaziabad", "faridabad", "sonipat",
    "rohtak", "hisar", "karnal", "panipat", "jalandhar", "pathankot", "shimla",
    "solan", "jammu", "srinagar", "raipur", "bilaspur", "jabalpur", "gwalior", "ujjain",
    "sagar", "satna", "rewa", "nanded", "solapur", "sangli", "amravati", "akola",
    "latur", "jalgaon", "dhule", "ahmednagar", "satara", "ratnagiri", "panaji",
    "margao", "kozhikode", "calicut", "thrissur", "kollam", "kottayam", "kannur",
    "palakkad", "alappuzha", "ernakulam", "salem", "tiruchirappalli", "trichy",
    "madurai", "tirunelveli", "vellore", "erode", "tiruppur", "pondicherry",
    "puducherry", "warangal", "nizamabad", "karimnagar", "khammam", "guntur",
    "nellore", "kurnool", "rajahmundry", "kakinada", "tirupati", "anantapur",
    "london", "new york", "san francisco", "seattle", "austin", "boston", "toronto",
    "vancouver", "singapore", "dubai", "abu dhabi", "doha", "riyadh", "berlin",
    "munich", "paris", "amsterdam", "dublin", "sydney", "melbourne", "tokyo",
}

LOCATION_LABEL_RE = re.compile(r"^(?:location|address|city|based in|residing in)\s*[:\-]\s*(.+)$", re.IGNORECASE)
CITY_STATE_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?),\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b")


def _extract_identity(text: str, sections: dict[str, list[str]]) -> dict:
    result: dict = {}

    emails = EMAIL_RE.findall(text)
    if emails:
        result["email"] = normalize_email(emails[0])

    phones: list[str] = []
    label_match = PHONE_LABEL_RE.search(text)
    if label_match:
        phones.append(label_match.group(1))
    head_text = "\n".join(sections.get("_header", [])[:20]) or "\n".join(text.split("\n")[:20])
    for candidate in PHONE_GENERIC_RE.findall(head_text):
        digits = re.sub(r"\D+", "", candidate)
        if 10 <= len(digits) <= 13:
            phones.append(candidate)
    if phones:
        result["phone"] = normalize_phone(phones[0])
        result["phone_raw"] = phones[0].strip()

    links: list[str] = []
    for match in URL_RE.findall(text):
        url = match.strip().rstrip(".,;")
        if "@" in url or url.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        if url and url.lower() not in (link.lower() for link in links):
            links.append(url if url.startswith("http") else f"https://{url}")
    result["links"] = links[:5]

    dob = DOB_RE.search(text)
    if dob:
        result["dob_text"] = dob.group(1).strip()

    name: str | None = None
    for line in text.split("\n")[:25]:
        label = NAME_LABEL_RE.match(line.strip())
        if label:
            candidate = label.group(1).strip()
            if NAME_WORD_RE.match(candidate) and candidate.lower() not in NAME_BLOCKLIST:
                name = candidate
                break
    if name is None:
        header_lines = sections.get("_header", []) or text.split("\n")[:15]
        for line in header_lines[:15]:
            stripped = line.strip().strip("#•-–—▪|").strip()
            if not stripped or len(stripped) > 45:
                continue
            if EMAIL_RE.search(stripped) or URL_RE.search(stripped) or any(ch.isdigit() for ch in stripped):
                continue
            lowered = stripped.lower()
            if lowered in NAME_BLOCKLIST or _heading_section(stripped):
                continue
            if NAME_WORD_RE.match(stripped):
                name = stripped
                break
    result["name"] = name

    location: str | None = None
    for line in text.split("\n")[:25]:
        match = LOCATION_LABEL_RE.match(line.strip())
        if match:
            location = match.group(1).strip().strip("|").strip()
            break
    if not location:
        for line in text.split("\n")[:25]:
            for city_match in CITY_STATE_RE.finditer(line):
                city = city_match.group(1).strip().lower()
                if city in KNOWN_CITIES:
                    location = f"{city_match.group(1).strip()}, {city_match.group(2).strip()}"
                    break
            if location:
                break
    if not location:
        for line in text.split("\n")[:25]:
            words = re.findall(r"[A-Za-z]+", line)
            for index, word in enumerate(words):
                if word.lower() in KNOWN_CITIES:
                    location = word.title()
                    break
            if location:
                break
    result["location"] = location
    return result


# --------------------------------------------------------------------------
# education
# --------------------------------------------------------------------------

DEGREE_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, short code, display name)
    (r"\b(mca|master of computer applications)\b", "MCA", "MCA — Master of Computer Applications"),
    (r"\b(bca|bachelor of computer applications)\b", "BCA", "BCA — Bachelor of Computer Applications"),
    (r"\b(mba|master of business administration)\b", "MBA", "MBA — Master of Business Administration"),
    (r"\b(bba|bachelor of business administration)\b", "BBA", "BBA — Bachelor of Business Administration"),
    (r"\b(m\.?\s?com|master of commerce)\b", "MCom", "MCom — Master of Commerce"),
    (r"\b(b\.?\s?com|bachelor of commerce)\b", "BCom", "BCom — Bachelor of Commerce"),
    (r"\b(m\.?\s?tech|master of technology)\b", "MTech", "MTech — Master of Technology"),
    (r"\b(b\.?\s?tech|bachelor of technology)\b", "BTech", "BTech — Bachelor of Technology"),
    (r"\b(b\.?\s?e\.?|bachelor of engineering)\b", "BE", "BE — Bachelor of Engineering"),
    (r"\b(m\.?\s?sc|master of science)\b", "MSc", "MSc — Master of Science"),
    (r"\b(b\.?\s?sc|bachelor of science)\b", "BSc", "BSc — Bachelor of Science"),
    (r"\b(m\.?\s?a\.?|master of arts)\b", "MA", "MA — Master of Arts"),
    (r"\b(b\.?\s?a\.?|bachelor of arts)\b", "BA", "BA — Bachelor of Arts"),
    (r"\b(ph\.?\s?d|doctorate)\b", "PhD", "PhD — Doctorate"),
    (r"\b(diploma)\b", "Diploma", "Diploma"),
    (r"\b(12th|hsc|higher secondary|intermediate|senior secondary|class xii)\b", "12th", "Higher Secondary (12th)"),
    (r"\b(10th|ssc|matriculation|secondary school|class x)\b", "10th", "Secondary School (10th)"),
]

ACADEMIC_LABELED_RE = re.compile(
    r"(?:cgpa|gpa|sgpa|grade point average)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)(?:\s*/\s*(\d{1,2}))?",
    re.IGNORECASE,
)
ACADEMIC_TRAILING_RE = re.compile(
    r"(\d{1,2}\.\d{1,2})\s*(?:/\s*10|/\s*out of 10)?\s*(?:cgpa|gpa|sgpa)\b", re.IGNORECASE
)
PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,2})?)\s*(?:%|percent)", re.IGNORECASE)
INSTITUTION_RE = re.compile(
    r"(university|college|institute|school|academy|polytechnic|iit|nit|iim|iiit|vit|srm|manipal|symbiosis)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _parse_academic_value(line: str) -> tuple[float | None, str | None]:
    match = ACADEMIC_LABELED_RE.search(line)
    if match:
        value = float(match.group(1))
        scale = float(match.group(2)) if match.group(2) else 10.0
        if scale and scale > 0:
            value = value * (10.0 / scale)
        if 0 <= value <= 10:
            return round(value, 2), "cgpa"
    match = ACADEMIC_TRAILING_RE.search(line)
    if match:
        value = float(match.group(1))
        if 0 <= value <= 10:
            return round(value, 2), "cgpa"
    match = PERCENT_RE.search(line)
    if match:
        value = float(match.group(1))
        if 0 <= value <= 100:
            return round(value, 2), "percentage"
    return None, None


def _extract_education(section_lines: list[str], whole_text: str) -> list[EducationItem]:
    items: list[EducationItem] = []
    lines = section_lines if section_lines else whole_text.split("\n")
    for index, line in enumerate(lines):
        found_degree: tuple[str, str] | None = None
        for pattern, code, display in DEGREE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                found_degree = (code, display)
                break
        if not found_degree:
            continue
        code, display = found_degree
        value, value_type = _parse_academic_value(line)
        if value is None:
            # academic value often sits on the line directly below the degree
            for offset in (1, 2):
                neighbour_index = index + offset
                if 0 <= neighbour_index < len(lines):
                    value, value_type = _parse_academic_value(lines[neighbour_index])
                    if value is not None:
                        break
        institution: str | None = None
        if INSTITUTION_RE.search(line):
            institution = line.strip("•-–—▪ ").strip()
        else:
            for offset in (1, -1, 2):
                neighbour_index = index + offset
                if 0 <= neighbour_index < len(lines) and INSTITUTION_RE.search(lines[neighbour_index]):
                    institution = lines[neighbour_index].strip("•-–—▪ ").strip()
                    break
        year: str | None = None
        year_match = YEAR_RE.search(line)
        if year_match:
            year = year_match.group(0)
        else:
            for offset in (1, 2):
                neighbour_index = index + offset
                if 0 <= neighbour_index < len(lines):
                    neighbour_years = YEAR_RE.findall(lines[neighbour_index])
                    if neighbour_years:
                        year = max(f"{prefix}{suffix}" for prefix, suffix in neighbour_years)
                        break
        items.append(
            EducationItem(
                degree=display,
                course=code,
                institution=institution[:160] if institution else None,
                graduation_year=year,
                academic_value=value,
                academic_type=value_type,
                raw_line=line.strip()[:300],
            )
        )
    # merge duplicates of the same course code (keep the first with a value)
    merged: dict[str, EducationItem] = {}
    for item in items:
        key = item.course or item.degree or item.raw_line
        if key in merged:
            existing = merged[key]
            if existing.academic_value is None and item.academic_value is not None:
                existing.academic_value = item.academic_value
                existing.academic_type = item.academic_type
            if not existing.institution and item.institution:
                existing.institution = item.institution
            if not existing.graduation_year and item.graduation_year:
                existing.graduation_year = item.graduation_year
        else:
            merged[key] = item
    return list(merged.values())


# --------------------------------------------------------------------------
# skills
# --------------------------------------------------------------------------

SKILL_SPLIT_RE = re.compile(r"[,;|•·▪●\u2022\n]|(?:\s{2,})|(?:\s-\s)")


def _extract_skills(skills_lines: list[str], experience_text: str, projects_text: str, whole_text: str) -> list[SkillItem]:
    listed: dict[str, SkillItem] = {}
    for line in skills_lines:
        for token in SKILL_SPLIT_RE.split(line):
            token = token.strip("•-–—▪*.: \t")
            token = re.sub(r"^(and|etc\.?)\s+", "", token, flags=re.IGNORECASE).strip()
            if not token or len(token) > 45:
                continue
            # drop proficiency notes like "Python (advanced)"
            token = re.sub(r"\s*\(.*?\)\s*$", "", token).strip()
            if not token:
                continue
            canonical, category = skills_lexicon.canonicalize(token)
            if not canonical:
                continue
            lowered = canonical.lower()
            if lowered in listed:
                if token not in listed[lowered].sources:
                    listed[lowered].sources.append("Skills section")
            else:
                listed[lowered] = SkillItem(
                    skill=canonical, category=category, strength="listed", sources=["Skills section"]
                )

    used_in_experience = {
        entry[0].lower() for entry in skills_lexicon.match_in_text(experience_text, skills_section=False)
    }
    used_in_projects = {
        entry[0].lower() for entry in skills_lexicon.match_in_text(projects_text, skills_section=False)
    }
    mentioned_everywhere = {
        entry[0].lower() for entry in skills_lexicon.match_in_text(whole_text, skills_section=False)
    }

    # upgrade/add skills based on usage evidence
    for lowered, item in listed.items():
        if lowered in used_in_experience:
            item.sources.append("Experience section")
        if lowered in used_in_projects:
            item.sources.append("Projects section")
        if lowered in used_in_experience or lowered in used_in_projects:
            item.strength = "strong"

    for entry in skills_lexicon.match_in_text(projects_text + "\n" + experience_text, skills_section=False):
        canonical, category, _aliases, _strict = entry
        lowered = canonical.lower()
        if lowered in listed:
            continue
        sources = []
        if lowered in used_in_projects:
            sources.append("Projects section")
        if lowered in used_in_experience:
            sources.append("Experience section")
        if lowered in mentioned_everywhere or sources:
            listed[lowered] = SkillItem(
                skill=canonical, category=category, strength="moderate", sources=sources or ["Mentioned in resume text"]
            )

    return sorted(listed.values(), key=lambda item: (item.category, item.skill.lower()))


# --------------------------------------------------------------------------
# experience / projects / certifications / achievements
# --------------------------------------------------------------------------

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
DATE_RANGE_RE = re.compile(
    rf"(?:(?:{MONTHS})[a-z]*\.?\s*[,']?\s*\d{{4}}|\d{{1,2}}[/-]\d{{4}}|\d{{4}})\s*(?:-|–|—|to|until)\s*(?:(?:{MONTHS})[a-z]*\.?\s*[,']?\s*\d{{4}}|\d{{1,2}}[/-]\d{{4}}|\d{{4}}|present|current|till date|ongoing|now)",
    re.IGNORECASE,
)
ROLE_RE = re.compile(
    r"(intern|engineer|developer|analyst|manager|executive|associate|trainee|consultant|designer|"
    r"architect|administrator|specialist|assistant|officer|lead|head|freelancer|volunteer|teacher|tutor|"
    r"accountant|auditor|advisor|coordinator|supervisor|programmer|scientist|researcher)",
    re.IGNORECASE,
)
ORG_RE = re.compile(
    r"(pvt|ltd|limited|inc|llp|corp|corporation|technologies|technology|solutions|systems|labs|"
    r"software|services|consulting|industries|enterprises|group|company|university|college|institute|"
    r"foundation|ngo|startup|studio|agency|bank|hospital)",
    re.IGNORECASE,
)
CERT_ISSUER_RE = re.compile(
    r"(coursera|udemy|nptel|edx|google|microsoft|aws|amazon|cisco|oracle|ibm|meta|hackerrank|"
    r"great learning|simplilearn|internshala|linkedin learning|udacity|pluralsight|sololearn|"
    r"red hat|comptia|pmi|scrum\.org|autodesk|adobe|salesforce|freecodecamp|coding ninjas|scaler|unacademy)",
    re.IGNORECASE,
)
CERT_WORD_RE = re.compile(r"(certificat|certified|credential|specialization|nanodegree|course completion)", re.IGNORECASE)
ACHIEVEMENT_RE = re.compile(
    r"(award|winner|won|rank|medal|scholarship|topper|merit|prize|trophy|champion|runner[- ]up|"
    r"selected|shortlisted|published|publication|paper presented|captain|president|secretary|"
    r"coordinator|organizer|organiser|volunteer|nss|leadership|position of|represented|"
    r"hackathon|olympiad|competition|conference)",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^\s*(?:[•▪●○◦*\-–—]|\d+[.)])\s+")
PLACEHOLDER_RE = re.compile(
    r"^(?:not\s+applicable|none|nil|n/?a|nothing\s+to\s+mention|"
    r"no\s+(?:major\s+)?(?:projects?|experience|internships?|certifications?|awards?|achievements?)"
    r"(?:\s+(?:completed|yet|done|available|so\s+far|as\s+such|as\s+of\s+now|till\s+date|to\s+date))*)\s*[.:]?\s*$",
    re.IGNORECASE,
)


def _month_index(name: str) -> int:
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    lowered = name.lower()[:3]
    return months.index(lowered) if lowered in months else 0


def _parse_date_token(token: str) -> tuple[int, int] | None:
    token = token.strip().lower()
    if token in ("present", "current", "till date", "ongoing", "now"):
        return None
    match = re.search(rf"({MONTHS})[a-z]*\.?\s*[,']?\s*(\d{{4}})", token)
    if match:
        return int(match.group(2)), _month_index(match.group(1))
    match = re.search(r"(\d{1,2})[/-](\d{4})", token)
    if match:
        return int(match.group(2)), int(match.group(1))
    match = re.search(r"(\d{4})", token)
    if match:
        return int(match.group(1)), 1
    return None


def _date_range(line: str) -> tuple[str | None, str | None, int | None]:
    match = DATE_RANGE_RE.search(line)
    if not match:
        return None, None, None
    raw = match.group(0)
    parts = re.split(r"\s*(?:-|–|—|to|until)\s*", raw, maxsplit=1)
    if len(parts) != 2:
        return None, None, None
    start_raw, end_raw = parts[0].strip(), parts[1].strip()
    start = _parse_date_token(start_raw)
    end_token = end_raw.lower()
    end = _parse_date_token(end_raw)
    if end is None and end_token not in ("present", "current", "till date", "ongoing", "now"):
        end = _parse_date_token(end_raw)
    duration = None
    if start and end:
        duration = max(0, (end[0] - start[0]) * 12 + (end[1] - start[1]))
    return start_raw, end_raw, duration


def _group_entries(lines: list[str]) -> list[list[str]]:
    """Group a section into entries: a bullet-free line starts a new entry."""
    entries: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or PLACEHOLDER_RE.match(stripped):
            continue
        if not entries:
            entries.append([stripped])
            continue
        if BULLET_RE.match(stripped):
            entries[-1].append(stripped)
            continue
        # a line that is purely a date range belongs to the previous entry
        without_dates = DATE_RANGE_RE.sub("", stripped).strip(" -–—|,")
        if DATE_RANGE_RE.search(stripped) and len(without_dates) < 6:
            entries[-1].append(stripped)
        else:
            entries.append([stripped])
    return entries


def _extract_experience(section_lines: list[str]) -> list[ExperienceItem]:
    items: list[ExperienceItem] = []
    for group in _group_entries(section_lines):
        head = group[0]
        body = "\n".join(group[1:])
        whole = "\n".join(group)
        if DATE_RANGE_RE.search(head):
            start, end, duration = _date_range(head)
        else:
            start, end, duration = _date_range(whole)
        title: str | None = None
        if ROLE_RE.search(head):
            title = head.split(" at ")[0].split(" | ")[0].split(" – ")[0].split(" - ")[0].strip("•-–—▪ ")[:120]
        else:
            for line in group[1:3]:
                if ROLE_RE.search(line):
                    title = line.strip("•-–—▪ ")[:120]
                    break
        organization: str | None = None
        for line in group[:3]:
            if ORG_RE.search(line):
                organization = line.strip("•-–—▪ ")[:120]
                break
        if not title and not organization and not DATE_RANGE_RE.search(whole) and len(group) == 1:
            continue  # stray line, not a real entry
        kind = "internship" if re.search(r"intern", whole, re.IGNORECASE) else "employment"
        items.append(
            ExperienceItem(
                title=title,
                organization=organization,
                kind=kind,
                start_date=start,
                end_date=end,
                duration_months=duration,
                description=body[:600],
                raw_text=whole[:1200],
            )
        )
    return items


PROJECT_TECH_HINT_RE = re.compile(r"(using|built with|technologies|tech stack|tools)\s*[:\-]?\s*(.+)$", re.IGNORECASE)


def _extract_projects(section_lines: list[str]) -> list[ProjectItem]:
    items: list[ProjectItem] = []
    for group in _group_entries(section_lines):
        head = group[0]
        body = "\n".join(group[1:])
        whole = "\n".join(group)
        name = head.split(":")[0].split("|")[0].split(" – ")[0].strip("•-–—▪ ")[:130]
        technologies: list[str] = []
        for entry in skills_lexicon.match_in_text(whole, skills_section=False):
            canonical, _category, _aliases, _strict = entry
            if canonical not in technologies:
                technologies.append(canonical)
        hint = PROJECT_TECH_HINT_RE.search(whole)
        if hint:
            for token in re.split(r"[,;|/]", hint.group(2)):
                token = token.strip(" .-")
                if token and 2 <= len(token) <= 40:
                    canonical, _category = skills_lexicon.canonicalize(token)
                    if canonical and canonical not in technologies:
                        technologies.append(canonical)
        if not name and not whole:
            continue
        items.append(
            ProjectItem(
                name=name or "Untitled project",
                technologies=technologies[:12],
                description=body[:600],
                raw_text=whole[:1200],
            )
        )
    return items


def _extract_certifications(section_lines: list[str]) -> list[CertificationItem]:
    items: list[CertificationItem] = []
    for line in section_lines:
        stripped = line.strip("•-–—▪ ")
        if not stripped:
            continue
        issuer_match = CERT_ISSUER_RE.search(stripped)
        has_cert_word = CERT_WORD_RE.search(stripped) is not None
        if not issuer_match and not has_cert_word:
            continue
        year_match = YEAR_RE.search(stripped)
        name = stripped
        if ":" in stripped and len(stripped.split(":")[0]) < 30:
            name = stripped.split(":", 1)[1].strip() or stripped
        items.append(
            CertificationItem(
                name=name[:200],
                issuer=issuer_match.group(0).title() if issuer_match else None,
                year=year_match.group(0) if year_match else None,
            )
        )
    return items


def _extract_achievements(section_lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in section_lines:
        stripped = line.strip("•-–—▪ ")
        if stripped and ACHIEVEMENT_RE.search(stripped):
            items.append(stripped[:300])
    return items[:12]


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def extract_resume(text: str) -> ExtractedResume:
    sections = split_sections(text)
    result = ExtractedResume()

    identity = _extract_identity(text, sections)
    result.name = identity.get("name")
    result.email = identity.get("email")
    result.phone = identity.get("phone")
    result.location = identity.get("location")
    result.links = identity.get("links", [])
    result.dob_text = identity.get("dob_text")

    experience_text = "\n".join(sections.get("experience", []))
    projects_text = "\n".join(sections.get("projects", []))

    result.education = _extract_education(sections.get("education", []), text)
    result.skills = _extract_skills(sections.get("skills", []), experience_text, projects_text, text)
    result.experience = _extract_experience(sections.get("experience", []))
    result.projects = _extract_projects(sections.get("projects", []))
    result.certifications = _extract_certifications(sections.get("certifications", []))
    result.achievements = _extract_achievements(sections.get("achievements", []))

    found: list[str] = []
    if result.name:
        found.append("name")
    if result.email:
        found.append("email")
    if result.phone:
        found.append("phone")
    if result.education:
        found.append("education")
    if result.best_academic() is not None:
        found.append("academic score")
    if result.skills:
        found.append("skills")
    if result.experience:
        found.append("experience")
    if result.projects:
        found.append("projects")
    if result.certifications:
        found.append("certifications")
    if result.achievements:
        found.append("achievements")
    result.sections_found = found
    return result
