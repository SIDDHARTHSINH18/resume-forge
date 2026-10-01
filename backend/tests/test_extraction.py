"""Structured extraction from resume text."""

from __future__ import annotations

from app.extraction import extract_resume

FULL_RESUME = """Aarav Patel
Ahmedabad, Gujarat | +91 98765 43210 | aarav@example.com | linkedin.com/in/aaravpatel
Date of Birth: 14/06/2003

SUMMARY
Final-year BCA student.

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, Ahmedabad, 2024
CGPA: 8.9/10
Higher Secondary (12th), Kendriya Vidyalaya, 2021 - 82%

SKILLS
Python, SQL, Git, React, HTML, CSS

EXPERIENCE
Web Development Intern at TechNova Solutions Pvt Ltd
Jun 2024 - Aug 2024
- Built REST APIs with Python and Flask.
- Wrote SQL queries against PostgreSQL.

PROJECTS
Student Management System using Python, SQL and Flask
- Full CRUD application.
Portfolio Website using React and HTML
- Deployed on GitHub Pages.

CERTIFICATIONS
Python for Everybody - Coursera, 2023

ACHIEVEMENTS
- Won 2nd prize in the university hackathon 2024
"""


def test_identity_extraction():
    result = extract_resume(FULL_RESUME)
    assert result.name == "Aarav Patel"
    assert result.email == "aarav@example.com"
    assert result.phone == "9876543210"
    assert result.location == "Ahmedabad, Gujarat"
    assert any("linkedin.com" in link for link in result.links)


def test_dob_is_captured_for_display_only():
    result = extract_resume(FULL_RESUME)
    assert result.dob_text is not None and "14/06/2003" in result.dob_text


def test_education_and_academic():
    result = extract_resume(FULL_RESUME)
    courses = [item.course for item in result.education]
    assert "BCA" in courses and "12th" in courses
    best = result.best_academic()
    assert best == (8.9, "cgpa")


def test_skills_with_strength_and_sources():
    result = extract_resume(FULL_RESUME)
    skills = {item.skill: item for item in result.skills}
    assert "Python" in skills
    assert skills["Python"].strength == "strong"  # listed + used in projects/experience
    assert any("Skills section" in source for source in skills["Python"].sources)
    assert skills["Git"].strength == "listed"  # listed but no usage evidence


def test_experience_extraction():
    result = extract_resume(FULL_RESUME)
    assert len(result.experience) == 1
    entry = result.experience[0]
    assert entry.kind == "internship"
    assert entry.start_date == "Jun 2024" and entry.end_date == "Aug 2024"
    assert entry.duration_months == 2
    assert "REST APIs" in entry.description


def test_projects_extraction():
    result = extract_resume(FULL_RESUME)
    names = " ".join(item.name or "" for item in result.projects)
    assert "Student Management System" in names
    assert any("Python" in item.technologies for item in result.projects)


def test_certifications_and_achievements():
    result = extract_resume(FULL_RESUME)
    assert result.certifications and "Coursera" in (result.certifications[0].issuer or "")
    assert result.certifications[0].year == "2023"
    assert any("hackathon" in item.lower() for item in result.achievements)


def test_sections_found_reports_missing_pieces():
    sparse = extract_resume("Some Person\nEmail: x@example.com\n\nSKILLS\nPython\n")
    assert "name" in sparse.sections_found
    assert "email" in sparse.sections_found
    assert "academic score" not in sparse.sections_found
    assert "projects" not in sparse.sections_found


def test_placeholder_lines_are_not_projects_or_experience():
    text = """Kabir Mehta
kabir@example.com

EDUCATION
Bachelor of Computer Applications (BCA), Saurashtra University, 2023
CGPA: 7.4

SKILLS
Python, MS Office

EXPERIENCE
Not applicable

PROJECTS
No major projects completed yet.
"""
    result = extract_resume(text)
    assert result.experience == []
    assert result.projects == []


def test_no_fabrication_when_fields_missing():
    result = extract_resume("A Person\nEmail: ap@example.com\n\nSKILLS\nPython\n")
    assert result.location is None
    assert result.phone is None
    assert result.best_academic() is None
    assert result.experience == []
