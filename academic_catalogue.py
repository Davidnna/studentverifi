"""Published Ebonyi State University academic catalogue and import aliases.

Reference: https://ebsu.edu.ng/faculties/ (reviewed 2026-11-20).
These are faculty/department labels from the university faculties listing,
not a guarantee that admissions programme labels are identical.  Aliases are
convenience mappings; review imported data before production use.

This module is deliberately independent of app.py (no circular import).
"""
import re
from collections import defaultdict

FACULTY_DEPARTMENTS = {
    "Science": (
        "Applied Biology", "Applied Microbiology", "Biochemistry", "Biotechnology",
        "Computer Science", "Geology / Exploration", "Industrial Chemistry",
        "Industrial Mathematics & Statistics", "Industrial Physics",
    ),
    "Agricultural and Natural Resource Management": (
        "Agricultural Economics & Extension", "Animal Science", "Fishery & Aqua-Culture",
        "Food Science & Technology", "Soil Science & Environmental Mgt",
    ),
    "Health Science and Technology": (
        "Medical Laboratory Science", "Nursing Science",
    ),
    "Social Sciences and Humanities": (
        "Economics", "English Language / Literature", "History & International Relations",
        "Language & Linguistics", "Library & Information Science", "Mass Communication",
        "Philosophy & Religion", "Political Science", "Psychology", "Social Works",
        "Sociology and Anthropology",
    ),
    "Basic Medical Sciences": ("Anatomy", "Medicine & Surgery", "Physiology"),
    "Clinical Medicine": ("Community Medicine", "Internal Medicine", "Pharmacology", "Surgery"),
    "Education": (
        "Arts / Social Science", "Business", "Educational Foundations",
        "Guidance & Counselling", "Home Economics", "Human Kinetic & Health Education",
        "Science Education", "Technology & Vocational Education",
    ),
    "Management Sciences": (
        "Accountancy", "Banking and Finance", "Business Management", "Marketing",
        "Public Administration",
    ),
    "Law": (
        "Business Law", "Civil Law", "International Law & Jurisprudence",
        "Private & Property Law", "Public Law",
    ),
    "Engineering": (
        "Electrical & Electronics Engineering", "Civil Engineering", "Building Technology",
        "Estate Management", "Chemical Engineering", "Architecture", "Environmental Sciences",
    ),
}

FACULTY_ALIASES = {
    "Faculty of Science": "Science",
    "Faculty of Agricultural and Natural Resource Mgt": "Agricultural and Natural Resource Management",
    "Agricultural and Natural Resource Mgt": "Agricultural and Natural Resource Management",
    "Agriculture": "Agricultural and Natural Resource Management",
    "Faculty of Health Science and Technology": "Health Science and Technology",
    "Health Sciences and Technology": "Health Science and Technology",
    "Faculty of Social Sciences and Humanities": "Social Sciences and Humanities",
    "Social Sciences": "Social Sciences and Humanities",
    "Faculty of Basic Medical Sciences": "Basic Medical Sciences",
    "Faculty of Clinical Medicine": "Clinical Medicine",
    "Faculty of Education": "Education",
    "Faculty of Management Sciences": "Management Sciences",
    "Faculty of Law": "Law",
    "Faculty of Engineering": "Engineering",
}

# Aliases map only alternative spellings or obvious abbreviations to published
# catalogue labels. Ambiguous names need their faculty supplied by the CSV.
DEPARTMENT_ALIASES = {
    "Biology": "Applied Biology",
    "Microbiology": "Applied Microbiology",
    "Geology": "Geology / Exploration",
    "Geology and Exploration": "Geology / Exploration",
    "Mathematics and Statistics": "Industrial Mathematics & Statistics",
    "Industrial Mathematics and Statistics": "Industrial Mathematics & Statistics",
    "Physics": "Industrial Physics",
    "Agricultural Economics and Extension": "Agricultural Economics & Extension",
    "Fisheries and Aquaculture": "Fishery & Aqua-Culture",
    "Fisheries & Aquaculture": "Fishery & Aqua-Culture",
    "Food Science and Technology": "Food Science & Technology",
    "Soil Science and Environmental Management": "Soil Science & Environmental Mgt",
    "Medical Laboratory Sciences": "Medical Laboratory Science",
    "Nursing": "Nursing Science",
    "English and Literary Studies": "English Language / Literature",
    "English Language and Literature": "English Language / Literature",
    "History and International Relations": "History & International Relations",
    "Languages and Linguistics": "Language & Linguistics",
    "Library and Information Science": "Library & Information Science",
    "Philosophy and Religion": "Philosophy & Religion",
    "Social Work": "Social Works",
    "Sociology & Anthropology": "Sociology and Anthropology",
    "Medicine and Surgery": "Medicine & Surgery",
    "Human Kinetics and Health Education": "Human Kinetic & Health Education",
    "Guidance and Counselling": "Guidance & Counselling",
    "Arts and Social Science": "Arts / Social Science",
    "Technology and Vocational Education": "Technology & Vocational Education",
    "Accounting": "Accountancy",
    "Electrical Engineering": "Electrical & Electronics Engineering",
    "Electrical and Electronics Engineering": "Electrical & Electronics Engineering",
    "Environmental Science": "Environmental Sciences",
}


def _key(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold().strip())


def _faculty_map():
    by_key = {}
    for name in FACULTY_DEPARTMENTS:
        by_key[_key(name)] = name
        by_key[_key("Faculty of " + name)] = name
    for alias, canonical in FACULTY_ALIASES.items():
        by_key[_key(alias)] = canonical
    return by_key


def resolve_faculty(value):
    """Return the published faculty name; reject unknown labels."""
    result = _faculty_map().get(_key(value))
    if not result:
        raise ValueError(f"Unrecognised EBSU faculty: {value!r}.")
    return result


def resolve_department(value, faculty=None):
    """Resolve a department and parent faculty, rejecting ambiguity."""
    key = _key(value)
    canonical_alias = DEPARTMENT_ALIASES.get(value)
    if canonical_alias:
        key = _key(canonical_alias)
    else:
        # Case- and punctuation-insensitive alias matching.
        for alias, canonical in DEPARTMENT_ALIASES.items():
            if _key(alias) == key:
                key = _key(canonical)
                break
    selected_faculty = resolve_faculty(faculty) if faculty else None
    matches = [(fac, dept) for fac, departments in FACULTY_DEPARTMENTS.items()
               for dept in departments if _key(dept) == key and
               (not selected_faculty or fac == selected_faculty)]
    if not matches:
        raise ValueError(f"Department {value!r} is not listed under the selected faculty.")
    if len(matches) != 1:
        raise ValueError(f"Department {value!r} is ambiguous; provide its faculty.")
    return matches[0]


def academic_catalogue_counts():
    return len(FACULTY_DEPARTMENTS), sum(map(len, FACULTY_DEPARTMENTS.values()))
