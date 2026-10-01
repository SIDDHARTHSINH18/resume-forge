"""Generation of the optional DEMO DATA set.

Creates ~10 clearly-labelled synthetic resumes (TXT, DOCX and PDF) plus one
deliberately corrupted PDF for testing graceful failure. These files are only
written to the demo folder; they are never inserted into the database
directly. The user uploads them through the normal upload flow, and every
file starts with a "DEMO DATA — SYNTHETIC RESUME" banner so demo records can
never be confused with real candidates.
"""

from __future__ import annotations

from pathlib import Path

BANNER = "DEMO DATA — SYNTHETIC RESUME (generated for testing, not a real person)"

RESUMES: list[tuple[str, str]] = [
    (
        "demo_01_aarav_patel.txt",
        """{banner}

Aarav Patel
Ahmedabad, Gujarat | +91 98250 11111 | aarav.patel@example-demo.com | linkedin.com/in/aarav-demo

SUMMARY
Final-year BCA student with hands-on experience in web development and data handling.

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, Ahmedabad
CGPA: 8.9/10
Higher Secondary (12th), Kendriya Vidyalaya, Ahmedabad, 2021 - 82%

SKILLS
Python, SQL, Git, React, HTML, CSS, Flask, Problem Solving

EXPERIENCE
Web Development Intern at TechNova Solutions Pvt Ltd
Jun 2024 - Aug 2024
- Built REST APIs with Python and Flask for an internal dashboard.
- Wrote SQL queries and reports against PostgreSQL.
- Used Git for version control and code reviews.

PROJECTS
Student Management System using Python, SQL and Flask
- Full CRUD application with authentication and reporting.
Portfolio Website using React, HTML and CSS
- Personal portfolio deployed on GitHub Pages.
Attendance Tracker using Python and SQLite
- Desktop tool for tracking attendance with export to CSV.

CERTIFICATIONS
Python for Everybody - Coursera, 2023
SQL (Intermediate) - HackerRank, 2024

ACHIEVEMENTS
- Won 2nd prize in the university hackathon, 2024
- Class representative for two semesters
""",
    ),
    (
        "demo_02_riya_shah.txt",
        """{banner}

Riya Shah
Surat, Gujarat | +91 98250 22222 | riya.shah@example-demo.com | github.com/riyademo

SUMMARY
MCA graduate focused on backend development and databases.

EDUCATION
Master of Computer Applications (MCA), Veer Narmad South Gujarat University
CGPA: 8.2/10
Bachelor of Computer Applications (BCA), VNSGU, 2022 - 8.1 CGPA

SKILLS
Python, SQL, Git, Django, Linux

EXPERIENCE
Software Intern at BlueOrbit Technologies
Jan 2024 - Jun 2024
- Maintained Django services and wrote SQL migrations.
- Automated report generation with Python scripts.

PROJECTS
Library Management System using Django and SQL
- Role-based access with fine calculation.
Chatbot Prototype using Python
- Rule-based chatbot for college FAQ.

CERTIFICATIONS
Django for Beginners - Udemy, 2023

ACHIEVEMENTS
- Volunteer coordinator at college tech fest 2023
""",
    ),
    (
        "demo_03_kabir_mehta.txt",
        """{banner}

Kabir Mehta
Rajkot, Gujarat | +91 98250 33333 | kabir.mehta@example-demo.com

OBJECTIVE
BCA graduate looking for an opportunity in the IT industry.

EDUCATION
Bachelor of Computer Applications (BCA), Saurashtra University, 2023
CGPA: 7.4

SKILLS
Python, MS Office, Communication

EXPERIENCE
Not applicable

PROJECTS
No major projects completed yet.

DECLARATION
I hereby declare that the above information is true.
""",
    ),
    (
        "demo_04_ananya_iyer.txt",
        """{banner}

Ananya Iyer
Bengaluru, Karnataka | +91 98250 44444 | ananya.iyer@example-demo.com | github.com/ananyademo

SUMMARY
BCA graduate (2024) with strong project experience in full-stack development.

EDUCATION
Bachelor of Computer Applications (BCA), Christ University, Bengaluru
CGPA: 9.1/10

SKILLS
Python, SQL, Git, React, FastAPI, AWS, Docker, HTML, CSS, JavaScript

EXPERIENCE
Software Engineering Intern at CloudNest Systems Pvt Ltd
May 2024 - Aug 2024
- Built FastAPI microservices consumed by a React front end.
- Deployed services to AWS EC2 with Docker.

PROJECTS
Expense Tracker using FastAPI, React and PostgreSQL
- JWT authentication, monthly analytics dashboard.
Recipe Sharing Platform using Python and SQL
- Search, ratings and image uploads.
Cloud Notes App using FastAPI and AWS S3
- Serverless storage with signed URLs.

CERTIFICATIONS
AWS Cloud Practitioner Essentials - AWS, 2024
Meta Front-End Developer - Coursera, 2023

ACHIEVEMENTS
- Winner, inter-college coding contest 2023
- Published a paper on web accessibility in the college journal
""",
    ),
    (
        "demo_05_devansh_joshi.txt",
        """{banner}

Devansh Joshi
Ahmedabad, Gujarat | +91 98250 55555 | devansh.joshi@example-demo.com

SUMMARY
B.Com graduate with an interest in business operations and analytics.

EDUCATION
Bachelor of Commerce (B.Com), Gujarat University, 2023
Percentage: 78%

SKILLS
Tally, Excel, Accounting, GST, Communication

EXPERIENCE
Accounts Intern at Shreeji Traders
Jul 2023 - Dec 2023
- Maintained ledgers and assisted with GST filings.

PROJECTS
Campus Retail Survey using Excel
- Prepared charts and summaries of student purchasing patterns.

CERTIFICATIONS
Tally Essential Level 2 - Tally Education, 2023

ACHIEVEMENTS
- Treasurer, college commerce association
""",
    ),
    (
        "demo_06_meera_nair.txt",
        """{banner}

Meera Nair
Kochi, Kerala | +91 98250 66666 | meera.nair@example-demo.com

SUMMARY
BCA final-year student, interested in data analysis.

EDUCATION
Bachelor of Computer Applications (BCA), Cochin University of Science and Technology
CGPA: 7.9/10

SKILLS
Python, SQL, Excel, Statistics, Matplotlib

EXPERIENCE
Data Intern at Insight Analytics LLP
Jun 2024 - Jul 2024
- Cleaned survey datasets with Python and pandas.
- Built Excel dashboards for the sales team.

PROJECTS
Sales Analysis using Python and SQL
- Analysed quarterly sales data and charted trends with Matplotlib.

CERTIFICATIONS
Data Analysis with Python - freeCodeCamp, 2024
""",
    ),
    (
        "demo_07_rohan_desai.txt",
        """{banner}

Rohan Desai
Ahmedabad, Gujarat | +91 98250 11111 | aarav.patel@example-demo.com | linkedin.com/in/aarav-demo

SUMMARY
Final-year BCA student with hands-on experience in web development and data handling.

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, Ahmedabad
CGPA: 8.9/10
Higher Secondary (12th), Kendriya Vidyalaya, Ahmedabad, 2021 - 82%

SKILLS
Python, SQL, Git, React, HTML, CSS, Flask, Problem Solving

EXPERIENCE
Web Development Intern at TechNova Solutions Pvt Ltd
Jun 2024 - Aug 2024
- Built REST APIs with Python and Flask for an internal dashboard.
- Wrote SQL queries and reports against PostgreSQL.
- Used Git for version control and code reviews.

PROJECTS
Student Management System using Python, SQL and Flask
- Full CRUD application with authentication and reporting.
Portfolio Website using React, HTML and CSS
- Personal portfolio deployed on GitHub Pages.
Attendance Tracker using Python and SQLite
- Desktop tool for tracking attendance with export to CSV.

CERTIFICATIONS
Python for Everybody - Coursera, 2023
SQL (Intermediate) - HackerRank, 2024
""",
    ),
    (
        "demo_08_sneha_kulkarni.txt",
        """{banner}

Sneha Kulkarni
Pune, Maharashtra | +91 98250 88888 | sneha.kulkarni@example-demo.com | github.com/sneha-demo

SUMMARY
BCA graduate with a strong project portfolio in web and mobile development.

EDUCATION
Bachelor of Computer Applications (BCA), Savitribai Phule Pune University
CGPA: 8.6/10

SKILLS
Python, SQL, Git, React, Flask, JavaScript, MongoDB

EXPERIENCE
Project Trainee at WebWorks Studio
Feb 2024 - May 2024
- Implemented front-end components in React for a client portal.
- Added Flask endpoints backed by MongoDB.

PROJECTS
Event Booking Portal using React, Flask and MongoDB
- Role-based booking flow with email confirmations.
Task Manager API using Python and SQL
- Token-authenticated REST API with test coverage.
Library Kiosk using Python
- Offline kiosk app for issue and return tracking.

CERTIFICATIONS
Full Stack Development Bootcamp - Udemy, 2024

ACHIEVEMENTS
- Runner-up, state-level project competition 2024
""",
    ),
    (
        "demo_09_arjun_singh.txt",
        """{banner}

Arjun Singh
Jaipur, Rajasthan | +91 98250 99999 | arjun.singh@example-demo.com

SUMMARY
BBA graduate interested in marketing and business development.

EDUCATION
Bachelor of Business Administration (BBA), University of Rajasthan, 2023
CGPA: 7.6/10

SKILLS
Marketing, Market Research, Excel, Communication, Canva

EXPERIENCE
Marketing Intern at BrightLeaf Media
Apr 2023 - Sep 2023
- Ran social media campaigns and prepared weekly performance reports.
- Assisted in market research for two product launches.

PROJECTS
Campus Brand Audit using Excel
- Surveyed 120 students and presented brand perception findings.

CERTIFICATIONS
Digital Marketing Fundamentals - Google, 2023

ACHIEVEMENTS
- Head of the college marketing club
""",
    ),
    (
        "demo_10_ishita_verma.txt",
        """{banner}

Ishita Verma
Lucknow, Uttar Pradesh | +91 98250 10101 | ishita.verma@example-demo.com | github.com/ishita-demo

SUMMARY
MCA post-graduate with internship experience in backend engineering.

EDUCATION
Master of Computer Applications (MCA), University of Lucknow
CGPA: 8.8/10
Bachelor of Computer Applications (BCA), University of Lucknow, 2022 - 8.2 CGPA

SKILLS
Python, SQL, Git, Docker, Flask, Linux, HTML, CSS

EXPERIENCE
Backend Intern at DataForge Analytics
Jan 2024 - Jul 2024
- Developed Flask services with SQLAlchemy and wrote SQL migrations.
- Containerised services with Docker for staging.

PROJECTS
Inventory API using Flask and SQL
- REST API with role-based auth and audit logging.
Result Portal using Python
- Bulk result processing with CSV export.

CERTIFICATIONS
Docker Essentials - IBM, 2024

ACHIEVEMENTS
- Merit scholarship for academic performance, 2023
""",
    ),
    (
        "demo_11_sumit_khan.txt",
        """{banner}

Sumit Khan
Bhopal, Madhya Pradesh | +91 98250 11223 | sumit.khan@example-demo.com

SUMMARY
BCA graduate seeking an entry-level software role.

EDUCATION
Bachelor of Computer Applications (BCA), Barkatullah University, 2023
CGPA: 6.8/10

SKILLS
HTML, CSS, MS Office

EXPERIENCE
Not applicable

PROJECTS
College Website using HTML and CSS
- Static website for the department with five pages.

DECLARATION
I hereby declare that the above information is true.
""",
    ),
]

DOCX_SOURCE = """{banner}

Priya Menon
Thiruvananthapuram, Kerala | +91 98250 77777 | priya.menon@example-demo.com | github.com/priyademo

SUMMARY
BCA final-year student with internship experience in quality assurance and automation.

EDUCATION
Bachelor of Computer Applications (BCA), University of Kerala
CGPA: 8.4/10

SKILLS
Python, SQL, Git, Selenium, Unit Testing, JavaScript

EXPERIENCE
QA Intern at QualiTest Labs
Jun 2024 - Aug 2024
- Wrote Selenium test suites for a web application.
- Logged and triaged defects in the tracker.

PROJECTS
Test Automation Suite using Python and Selenium
- Covered 40+ scenarios with HTML reports.
Result Scraper using Python
- Parsed university results and exported CSV summaries.

CERTIFICATIONS
Selenium WebDriver with Python - Udemy, 2024
"""

PDF_SOURCE = """{banner}

Nikhil Reddy
Hyderabad, Telangana | +91 98250 12121 | nikhil.reddy@example-demo.com | linkedin.com/in/nikhil-demo

SUMMARY
BCA graduate with strong fundamentals and two internships.

EDUCATION
Bachelor of Computer Applications (BCA), Osmania University
CGPA: 8.0/10

SKILLS
Python, SQL, Git, Flask, HTML, CSS

EXPERIENCE
Software Intern at Deccan Softworks
Jan 2024 - Apr 2024
- Added Flask endpoints and SQL reports for an internal tool.
Web Intern at Summit Digital
Jun 2023 - Aug 2023
- Built responsive pages with HTML and CSS.

PROJECTS
Student Portal using Flask and SQL
- Attendance and marks modules with role-based access.
Expense Splitter using Python
- Console tool with SQLite storage.

CERTIFICATIONS
Python Programming - NPTEL, 2023
"""


def _write_simple_pdf(path: Path, lines: list[str]) -> None:
    """Write a minimal, valid single-page PDF with Helvetica text."""
    def esc(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content_lines = ["BT", "/F1 10 Tf", "14 TL", "50 760 Td"]
    for line in lines:
        content_lines.append(f"({esc(line)}) Tj T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    buffer = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_start = len(buffer)
    buffer += f"xref\n0 {len(objects) + 1}\n".encode()
    buffer += b"0000000000 65535 f \n"
    for offset in offsets:
        buffer += f"{offset:010d} 00000 n \n".encode()
    buffer += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(buffer))


def _write_docx(path: Path, text: str) -> None:
    import docx

    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    document.save(str(path))


def _write_broken_pdf(path: Path) -> None:
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        + bytes(range(40, 200))
        + b"\ntrailer\n<< /Size 2 >>\n%%EOF\n"
    )


def generate_demo_resumes(target_dir: Path) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []

    for filename, template in RESUMES:
        path = target_dir / filename
        path.write_text(template.format(banner=BANNER), encoding="utf-8")
        written.append({"filename": filename, "kind": "txt", "bytes": path.stat().st_size})

    docx_path = target_dir / "demo_12_priya_menon.docx"
    _write_docx(docx_path, DOCX_SOURCE.format(banner=BANNER))
    written.append({"filename": docx_path.name, "kind": "docx", "bytes": docx_path.stat().st_size})

    pdf_path = target_dir / "demo_13_nikhil_reddy.pdf"
    _write_simple_pdf(pdf_path, PDF_SOURCE.format(banner=BANNER).split("\n"))
    written.append({"filename": pdf_path.name, "kind": "pdf", "bytes": pdf_path.stat().st_size})

    broken_path = target_dir / "demo_99_broken_resume.pdf"
    _write_broken_pdf(broken_path)
    written.append({"filename": broken_path.name, "kind": "broken-pdf", "bytes": broken_path.stat().st_size})

    return {"directory": str(target_dir), "files": written, "count": len(written)}


def demo_status(ctx) -> dict:
    directory = Path(ctx.demo_dir)
    files = []
    if directory.exists():
        for path in sorted(directory.iterdir()):
            if path.is_file():
                files.append({"filename": path.name, "bytes": path.stat().st_size})
    return {"directory": str(directory), "exists": directory.exists(), "files": files, "count": len(files)}
