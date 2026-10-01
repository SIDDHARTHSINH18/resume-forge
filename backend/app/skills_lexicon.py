"""Curated skill lexicon used by extraction and matching.

Each entry: (canonical name, category, pipe-separated aliases).
`strict` entries only match inside skills-section lines because the alias is
too ambiguous to trust in free text (e.g. single letters, common words).

This lexicon is a matching aid, not an authority: any skill named by a
screening profile is also matched directly (word-boundary) against resume
text, so profile-specific tools outside this list still work.
"""

from __future__ import annotations

import re

Entry = tuple[str, str, str, bool]  # canonical, category, aliases, strict

_RAW: list[tuple[str, str, str]] = [
    # --- programming languages ---
    ("Python", "programming_language", "python|python3|python 3"),
    ("Java", "programming_language", "java"),
    ("JavaScript", "programming_language", "javascript|js|java script|es6"),
    ("TypeScript", "programming_language", "typescript|ts"),
    ("C", "programming_language", "c programming|c language|c/c++|c and c++"),
    ("C++", "programming_language", "c++|cpp"),
    ("C#", "programming_language", "c#|c sharp"),
    ("Go", "programming_language", "golang|go programming|go language"),
    ("Rust", "programming_language", "rust"),
    ("PHP", "programming_language", "php"),
    ("Ruby", "programming_language", "ruby|ruby on rails|rails"),
    ("Kotlin", "programming_language", "kotlin"),
    ("Swift", "programming_language", "swift"),
    ("R", "programming_language", "r programming|r language|rstudio"),
    ("MATLAB", "programming_language", "matlab"),
    ("Scala", "programming_language", "scala"),
    ("Perl", "programming_language", "perl"),
    ("Dart", "programming_language", "dart"),
    ("Bash", "programming_language", "bash|shell scripting|shell script"),
    ("VBA", "programming_language", "vba|visual basic"),
    # --- frontend ---
    ("React", "web_frontend", "react|react.js|reactjs|react js"),
    ("Angular", "web_frontend", "angular|angularjs"),
    ("Vue", "web_frontend", "vue|vue.js|vuejs"),
    ("Next.js", "web_frontend", "next.js|nextjs"),
    ("HTML", "web_frontend", "html|html5"),
    ("CSS", "web_frontend", "css|css3|scss|sass|tailwind|tailwindcss|bootstrap"),
    ("Redux", "web_frontend", "redux"),
    ("jQuery", "web_frontend", "jquery"),
    # --- backend / frameworks ---
    ("Node.js", "web_backend", "node.js|nodejs|node js"),
    ("Express", "web_backend", "express.js|expressjs|express js"),
    ("Django", "web_backend", "django"),
    ("Flask", "web_backend", "flask"),
    ("FastAPI", "web_backend", "fastapi"),
    ("Spring", "web_backend", "spring boot|springboot|spring framework|spring"),
    ("ASP.NET", "web_backend", ".net|dotnet|asp.net|asp net"),
    ("Laravel", "web_backend", "laravel"),
    ("REST API", "web_backend", "rest api|restful|rest apis|api development"),
    ("GraphQL", "web_backend", "graphql"),
    # --- databases ---
    ("SQL", "database", "sql"),
    ("MySQL", "database", "mysql"),
    ("PostgreSQL", "database", "postgresql|postgres"),
    ("SQLite", "database", "sqlite"),
    ("MongoDB", "database", "mongodb|mongo db|mongo"),
    ("Oracle DB", "database", "oracle db|oracle database|oracle sql|pl/sql|plsql"),
    ("SQL Server", "database", "sql server|mssql|t-sql"),
    ("Redis", "database", "redis"),
    ("Firebase", "database", "firebase|firestore"),
    ("Supabase", "database", "supabase"),
    ("NoSQL", "database", "nosql"),
    # --- data / AI ---
    ("Data Analysis", "data_ai", "data analysis|data analytics|data analyst"),
    ("Pandas", "data_ai", "pandas"),
    ("NumPy", "data_ai", "numpy"),
    ("Matplotlib", "data_ai", "matplotlib"),
    ("Scikit-learn", "data_ai", "scikit-learn|sklearn|scikit learn"),
    ("TensorFlow", "data_ai", "tensorflow"),
    ("PyTorch", "data_ai", "pytorch|torch"),
    ("Keras", "data_ai", "keras"),
    ("Machine Learning", "data_ai", "machine learning|ml models"),
    ("Deep Learning", "data_ai", "deep learning|neural networks"),
    ("NLP", "data_ai", "nlp|natural language processing"),
    ("Computer Vision", "data_ai", "computer vision|opencv"),
    ("LLM", "data_ai", "llm|large language model|generative ai|genai|langchain"),
    ("Power BI", "data_ai", "power bi|powerbi"),
    ("Tableau", "data_ai", "tableau"),
    ("Excel", "data_ai", "excel|ms excel|microsoft excel|advanced excel|spreadsheets"),
    ("Statistics", "data_ai", "statistics|statistical analysis|probability"),
    ("Data Visualization", "data_ai", "data visualization|data visualisation|dashboarding"),
    ("ETL", "data_ai", "etl|data pipeline|data pipelines|data warehousing"),
    ("Big Data", "data_ai", "hadoop|spark|apache spark|big data"),
    # --- cloud / devops ---
    ("AWS", "cloud_devops", "aws|amazon web services|ec2|s3 bucket"),
    ("Azure", "cloud_devops", "azure|microsoft azure"),
    ("Google Cloud", "cloud_devops", "gcp|google cloud|google cloud platform"),
    ("Docker", "cloud_devops", "docker|containerization|containers"),
    ("Kubernetes", "cloud_devops", "kubernetes|k8s"),
    ("CI/CD", "cloud_devops", "ci/cd|cicd|continuous integration|continuous deployment|jenkins|github actions|gitlab ci"),
    ("Linux", "cloud_devops", "linux|ubuntu|unix"),
    # Platforms and umbrella terms are deliberately separate skills: a resume
    # that says "GitHub" is not assumed to prove "Git" and vice versa.
    ("Git", "cloud_devops", "git"),
    ("GitHub", "cloud_devops", "github|github pages|github actions"),
    ("GitLab", "cloud_devops", "gitlab"),
    ("Bitbucket", "cloud_devops", "bitbucket"),
    ("Version Control", "cloud_devops", "version control|vcs"),
    ("Networking", "cloud_devops", "networking|tcp/ip|dns|computer networks"),
    ("Serverless", "cloud_devops", "serverless|lambda functions|cloud functions"),
    ("Terraform", "cloud_devops", "terraform|infrastructure as code"),
    # --- mobile ---
    ("Android", "mobile", "android|android development|android studio"),
    ("iOS", "mobile", "ios development|ios app"),
    ("Flutter", "mobile", "flutter"),
    ("React Native", "mobile", "react native"),
    # --- testing / quality ---
    ("Unit Testing", "testing", "unit testing|unit tests|pytest|junit|jest|test driven"),
    ("Selenium", "testing", "selenium"),
    ("Manual Testing", "testing", "manual testing|qa testing|quality assurance"),
    ("Postman", "testing", "postman"),
    # --- tools / design ---
    ("Figma", "design", "figma"),
    ("UI/UX Design", "design", "ui/ux|ui design|ux design|user experience|wireframing|prototyping"),
    ("Photoshop", "design", "photoshop|adobe photoshop"),
    ("Canva", "design", "canva"),
    ("AutoCAD", "design", "autocad"),
    ("Tally", "finance", "tally|tally erp"),
    # --- business / management / commerce ---
    ("Accounting", "accounting", "accounting|accounts|bookkeeping|journal entries|ledger"),
    ("Finance", "finance", "finance|financial analysis|financial modelling|financial modeling|corporate finance"),
    ("GST", "accounting", "gst|taxation|income tax|tax filing"),
    ("Auditing", "accounting", "auditing|audit|internal audit"),
    ("Banking", "finance", "banking|banking operations|nbfc"),
    ("Economics", "finance", "economics|microeconomics|macroeconomics"),
    ("Business Analysis", "business", "business analysis|business analyst|requirement gathering|brd"),
    ("Marketing", "business", "marketing|digital marketing|seo|social media marketing|content marketing|brand"),
    ("Sales", "business", "sales|business development|lead generation|client acquisition"),
    ("Market Research", "business", "market research|competitor analysis|survey"),
    ("Project Management", "management", "project management|agile|scrum|kanban|jira|waterfall"),
    ("Product Management", "management", "product management|product owner|roadmap"),
    ("Operations", "management", "operations|supply chain|logistics|inventory management"),
    ("HR", "management", "human resources|hr operations|recruitment|talent acquisition|payroll"),
    ("Customer Service", "communication", "customer service|customer support|client handling|client servicing"),
    ("Communication", "communication", "communication skills|public speaking|presentation skills|anchoring|debate|elocution"),
    ("Leadership", "management", "leadership|team lead|team management|event management|student council|head of"),
    ("Business Knowledge", "business", "business studies|business environment|commerce|business management"),
    ("Entrepreneurship", "business", "entrepreneurship|startup|start-up"),
    # --- academic / fundamentals ---
    ("Mathematics", "mathematics", "mathematics|maths|quantitative aptitude|algebra|calculus|discrete mathematics"),
    ("Computer Fundamentals", "computer_fundamentals",
     "computer fundamentals|computer science fundamentals|operating systems|data structures|algorithms|dbms|oops|object oriented programming|computer organization"),
    ("Physics", "academic", "physics"),
    ("Chemistry", "academic", "chemistry"),
    ("Biology", "academic", "biology"),
    ("English", "academic", "english literature|english language|business english"),
]

# Aliases that must only be trusted inside a Skills section line.
_STRICT_CANONICALS = {"C", "R", "Go", "Swift", "Bash", "CSS", "Excel", "Statistics"}

SKILL_ENTRIES: list[Entry] = []
ALIAS_TO_SKILL: dict[str, Entry] = {}
CATEGORY_OF: dict[str, str] = {}


def _compile_matcher(alias: str) -> re.Pattern:
    escaped = re.escape(alias)
    if alias.endswith("+") or alias.endswith("#") or alias.endswith("."):
        pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    else:
        pattern = rf"(?<![A-Za-z0-9+#.]){escaped}(?![A-Za-z0-9+#])"
    return re.compile(pattern, re.IGNORECASE)


MATCHERS: dict[str, re.Pattern] = {}

for canonical, category, aliases in _RAW:
    strict = canonical in _STRICT_CANONICALS
    entry: Entry = (canonical, category, aliases, strict)
    SKILL_ENTRIES.append(entry)
    CATEGORY_OF[canonical.lower()] = category
    for alias in aliases.split("|"):
        alias = alias.strip()
        if not alias:
            continue
        ALIAS_TO_SKILL[alias] = entry
        MATCHERS[alias] = _compile_matcher(alias)


def canonicalize(raw_skill: str) -> tuple[str, str]:
    """Return (canonical_name, category) for a free-form skill string."""
    cleaned = re.sub(r"\s+", " ", (raw_skill or "").strip())
    if not cleaned:
        return "", "general"
    lowered = cleaned.lower()
    if lowered in ALIAS_TO_SKILL:
        canonical, category, _aliases, _strict = ALIAS_TO_SKILL[lowered]
        return canonical, category
    # strip trailing punctuation variants like "React.js," etc.
    trimmed = lowered.strip(" .,;:•-")
    if trimmed in ALIAS_TO_SKILL:
        canonical, category, _aliases, _strict = ALIAS_TO_SKILL[trimmed]
        return canonical, category
    return cleaned[:60], "general"


def match_in_text(text: str, *, skills_section: bool) -> list[Entry]:
    """Find lexicon skills inside text; strict entries only in skills sections."""
    if not text:
        return []
    found: set[str] = set()
    results: list[Entry] = []
    for alias, entry in ALIAS_TO_SKILL.items():
        canonical, _category, _aliases, strict = entry
        if canonical in found:
            continue
        if strict and not skills_section:
            continue
        if MATCHERS[alias].search(text):
            found.add(canonical)
            results.append(entry)
    return results
