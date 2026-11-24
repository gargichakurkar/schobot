import re


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize(value):
    """
    Convert a value into clean lowercase text.
    """

    if value is None:
        return ""

    return str(value).strip().lower()


def get_scholarship_text(scholarship):
    """
    Combine all useful scholarship fields into one searchable text.
    """

    parts = [
        scholarship.scheme_name,
        scholarship.eligibility,
        scholarship.details,
        scholarship.tags,
        scholarship.application_process,
        scholarship.benefits,
        scholarship.target_states,
        scholarship.department
    ]

    return " ".join(
        str(part)
        for part in parts
        if part
    ).lower()


def contains_phrase(text, phrase):
    """
    Safer phrase matching.
    """

    text = normalize(text)
    phrase = normalize(phrase)

    if not text or not phrase:
        return False

    pattern = r"\b" + re.escape(phrase) + r"\b"

    return re.search(pattern, text) is not None


def contains_any_phrase(text, phrases):
    """
    Check whether any phrase exists in text.
    """

    for phrase in phrases:

        if contains_phrase(text, phrase):
            return True

    return False


# ============================================================
# STATE
# ============================================================

def check_state(student, scholarship):

    student_state = normalize(student.state)

    if not student_state:
        return "unknown"

    text = " ".join([
        normalize(scholarship.target_states),
        normalize(scholarship.eligibility),
        normalize(scholarship.details)
    ])

    if not text.strip():
        return "unknown"

    national_keywords = [
        "all india",
        "all-india",
        "across india",
        "throughout india",
        "any state",
        "all states",
        "students across the country",
        "nationwide"
    ]

    if contains_any_phrase(
        text,
        national_keywords
    ):
        return "satisfied"

    if contains_phrase(
        text,
        student_state
    ):
        return "satisfied"

    return "unknown"


# ============================================================
# CATEGORY
# ============================================================

def check_category(student, scholarship):

    category = normalize(student.category)

    if not category:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    category_map = {

        "general": [
            "general category",
            "open category",
            "general students"
        ],

        "obc": [
            "obc",
            "other backward class",
            "other backward classes"
        ],

        "sc": [
            "scheduled caste",
            "scheduled castes",
            "sc category"
        ],

        "st": [
            "scheduled tribe",
            "scheduled tribes",
            "st category"
        ],

        "ews": [
            "ews",
            "economically weaker section",
            "economically weaker sections"
        ]
    }

    phrases = category_map.get(
        category,
        [category]
    )

    if contains_any_phrase(
        text,
        phrases
    ):
        return "satisfied"

    # Do not mark as not-eligible just because
    # the category was not found.
    return "unknown"


# ============================================================
# QUALIFICATION
# ============================================================

def check_qualification(student, scholarship):

    qualification = normalize(
        student.qualification
    )

    if not qualification:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    qualification_map = {

        "10th": [
            "10th",
            "class 10",
            "class x",
            "ssc",
            "secondary school"
        ],

        "12th": [
            "12th",
            "class 12",
            "class xii",
            "hsc",
            "higher secondary",
            "senior secondary"
        ],

        "diploma": [
            "diploma"
        ],

        "undergraduate": [
            "undergraduate",
            "graduation",
            "bachelor",
            "b.tech",
            "b.e",
            "degree"
        ],

        "graduate": [
            "graduate",
            "graduation",
            "bachelor",
            "b.tech",
            "b.e",
            "degree"
        ],

        "postgraduate": [
            "postgraduate",
            "post graduate",
            "master",
            "m.tech",
            "m.e",
            "mba",
            "m.sc",
            "msc",
            "degree"
        ],

        "phd": [
            "phd",
            "p.hd",
            "doctorate",
            "doctoral"
        ]
    }

    phrases = qualification_map.get(
        qualification,
        [qualification]
    )

    if contains_any_phrase(
        text,
        phrases
    ):
        return "satisfied"

    return "unknown"


# ============================================================
# EDUCATION STAGE
# ============================================================

def check_education_stage(
    student,
    scholarship
):

    stage = normalize(
        student.education_stage
    )

    if not stage:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    stage_map = {

        "school": [
            "school students",
            "school student",
            "school education",
            "secondary school",
            "higher secondary",
            "class 10",
            "class 12"
        ],

        "undergraduate": [
            "undergraduate",
            "under graduate",
            "graduation",
            "bachelor",
            "b.tech",
            "b.e"
        ],

        "postgraduate": [
            "postgraduate",
            "post graduate",
            "master",
            "m.tech",
            "m.e",
            "mba",
            "m.sc"
        ],

        "diploma": [
            "diploma students",
            "diploma course",
            "diploma"
        ],

        "phd": [
            "phd",
            "doctorate",
            "doctoral"
        ]
    }

    phrases = stage_map.get(
        stage,
        [stage]
    )

    if contains_any_phrase(
        text,
        phrases
    ):
        return "satisfied"

    return "unknown"


# ============================================================
# COURSE
# ============================================================

def check_course(student, scholarship):

    course = normalize(
        student.course
    )

    if not course:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    # Exact course match
    if contains_phrase(
        text,
        course
    ):
        return "satisfied"

    # Course keywords
    course_keywords = [
        word
        for word in re.findall(
            r"[a-z0-9]+",
            course
        )
        if len(word) >= 4
    ]

    if not course_keywords:
        return "unknown"

    matched = sum(
        1
        for word in course_keywords
        if contains_phrase(text, word)
    )

    # Require meaningful matching
    if len(course_keywords) >= 2:
        if matched >= 2:
            return "satisfied"

    elif matched == 1:
        return "satisfied"

    return "unknown"


# ============================================================
# STREAM
# ============================================================

def check_stream(student, scholarship):

    stream = normalize(
        student.stream
    )

    if not stream:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    stream_map = {

        "engineering": [
            "engineering",
            "b.tech",
            "b.e",
            "technology"
        ],

        "science": [
            "science",
            "scientific",
            "physics",
            "chemistry",
            "mathematics",
            "biology"
        ],

        "commerce": [
            "commerce",
            "accountancy",
            "business studies"
        ],

        "arts": [
            "arts",
            "humanities",
            "social science"
        ],

        "medical": [
            "medical",
            "medicine",
            "mbbs",
            "health sciences"
        ],

        "management": [
            "management",
            "business administration",
            "mba"
        ]
    }

    phrases = stream_map.get(
        stream,
        [stream]
    )

    if contains_any_phrase(
        text,
        phrases
    ):
        return "satisfied"

    return "unknown"


# ============================================================
# INCOME
# ============================================================

def extract_income_limits(text):

    if not text:
        return []

    text = text.lower()

    patterns = [

        r"income\s*(?:limit|should not exceed|must not exceed|less than|below|up to)?\s*[:\-]?\s*₹?\s*([\d,]+)",

        r"₹\s*([\d,]+)\s*(?:per annum|annually|per year)?",

        r"rs\.?\s*([\d,]+)\s*(?:per annum|annually|per year)?",

        r"family income.*?([\d,]+)",

        r"annual income.*?([\d,]+)"
    ]

    limits = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text
        )

        for value in matches:

            try:

                number = float(
                    value.replace(",", "")
                )

                # Ignore obviously unrelated tiny numbers
                if number >= 10000:
                    limits.append(number)

            except ValueError:
                continue

    return list(set(limits))


def check_income(student, scholarship):

    income = student.family_income

    if income is None:
        return "unknown"

    text = scholarship.eligibility or ""

    limits = extract_income_limits(
        text
    )

    if not limits:
        return "unknown"

    # If multiple limits appear,
    # use the lowest explicit income ceiling.
    limit = min(limits)

    if income <= limit:
        return "satisfied"

    return "not_satisfied"


# ============================================================
# PERCENTAGE
# ============================================================

def extract_percentage_limits(text):

    if not text:
        return []

    text = text.lower()

    patterns = [

        r"minimum\s*(?:percentage|marks|score)?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*%",

        r"at least\s*(\d+(?:\.\d+)?)\s*%",

        r"(\d+(?:\.\d+)?)\s*%\s*(?:or above|and above|minimum)",

        r"minimum.*?(\d+(?:\.\d+)?)\s*%"
    ]

    limits = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text
        )

        for value in matches:

            try:
                limits.append(
                    float(value)
                )
            except ValueError:
                continue

    return list(set(limits))


def check_percentage(student, scholarship):

    percentage = student.percentage

    if percentage is None:
        return "unknown"

    text = scholarship.eligibility or ""

    limits = extract_percentage_limits(
        text
    )

    if not limits:
        return "unknown"

    limit = max(limits)

    if percentage >= limit:
        return "satisfied"

    return "not_satisfied"


# ============================================================
# DISABILITY
# ============================================================

def check_disability(student, scholarship):

    disability = normalize(
        student.disability
    )

    if not disability:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    keywords = [
        "disability",
        "disabled",
        "divyang",
        "persons with disabilities",
        "person with disability",
        "pwd"
    ]

    scholarship_mentions_disability = (
        contains_any_phrase(
            text,
            keywords
        )
    )

    if disability in [
        "yes",
        "true"
    ]:

        if scholarship_mentions_disability:
            return "satisfied"

        return "unknown"

    if disability in [
        "no",
        "false"
    ]:

        if scholarship_mentions_disability:
            return "unknown"

        return "satisfied"

    return "unknown"


# ============================================================
# MINORITY
# ============================================================

def check_minority(student, scholarship):

    minority = normalize(
        student.minority
    )

    if not minority:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    keywords = [
        "minority",
        "minorities",
        "minority community"
    ]

    mentions_minority = (
        contains_any_phrase(
            text,
            keywords
        )
    )

    if minority in [
        "yes",
        "true"
    ]:

        if mentions_minority:
            return "satisfied"

        return "unknown"

    if minority in [
        "no",
        "false"
    ]:

        if mentions_minority:
            return "unknown"

        return "satisfied"

    return "unknown"


# ============================================================
# SPORTS
# ============================================================

def check_sports(student, scholarship):

    sports = normalize(
        student.sports
    )

    if not sports:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    keywords = [
        "sports",
        "sportsperson",
        "sports person",
        "athlete",
        "athletes",
        "sports achievement"
    ]

    mentions_sports = (
        contains_any_phrase(
            text,
            keywords
        )
    )

    if sports in [
        "yes",
        "true"
    ]:

        if mentions_sports:
            return "satisfied"

        return "unknown"

    if sports in [
        "no",
        "false"
    ]:

        if mentions_sports:
            return "unknown"

        return "satisfied"

    return "unknown"


# ============================================================
# EX-SERVICEMAN
# ============================================================

def check_exserviceman(
    student,
    scholarship
):

    status = normalize(
        student.exserviceman
    )

    if not status:
        return "unknown"

    text = get_scholarship_text(
        scholarship
    )

    keywords = [
        "ex-serviceman",
        "ex serviceman",
        "ex-servicemen",
        "armed forces",
        "defence personnel",
        "defense personnel",
        "military personnel"
    ]

    mentions_exserviceman = (
        contains_any_phrase(
            text,
            keywords
        )
    )

    if status in [
        "yes",
        "true"
    ]:

        if mentions_exserviceman:
            return "satisfied"

        return "unknown"

    if status in [
        "no",
        "false"
    ]:

        if mentions_exserviceman:
            return "unknown"

        return "satisfied"

    return "unknown"


# ============================================================
# AGE
# ============================================================

def extract_age_limit(text):

    if not text:
        return None, None

    text = text.lower()

    min_age = None
    max_age = None

    patterns_min = [
        r"minimum age.*?(\d+)",
        r"age.*?at least.*?(\d+)",
        r"above (\d+) years",
        r"(\d+) years and above"
    ]

    patterns_max = [
        r"maximum age.*?(\d+)",
        r"age.*?below.*?(\d+)",
        r"age.*?less than.*?(\d+)",
        r"under (\d+) years",
        r"up to (\d+) years"
    ]

    for pattern in patterns_min:

        match = re.search(
            pattern,
            text
        )

        if match:

            try:
                min_age = int(
                    match.group(1)
                )
                break
            except ValueError:
                pass

    for pattern in patterns_max:

        match = re.search(
            pattern,
            text
        )

        if match:

            try:
                max_age = int(
                    match.group(1)
                )
                break
            except ValueError:
                pass

    return min_age, max_age


def check_age(student, scholarship):

    age = student.age

    if age is None:
        return "unknown"

    text = scholarship.eligibility or ""

    min_age, max_age = extract_age_limit(
        text
    )

    if min_age is None and max_age is None:
        return "unknown"

    if min_age is not None and age < min_age:
        return "not_satisfied"

    if max_age is not None and age > max_age:
        return "not_satisfied"

    return "satisfied"


# ============================================================
# MAIN EVALUATION
# ============================================================

def evaluate_scholarship(
    student,
    scholarship
):

    conditions = {

        "age":
            check_age(
                student,
                scholarship
            ),

        "state":
            check_state(
                student,
                scholarship
            ),

        "category":
            check_category(
                student,
                scholarship
            ),

        "income":
            check_income(
                student,
                scholarship
            ),

        "qualification":
            check_qualification(
                student,
                scholarship
            ),

        "education_stage":
            check_education_stage(
                student,
                scholarship
            ),

        "course":
            check_course(
                student,
                scholarship
            ),

        "stream":
            check_stream(
                student,
                scholarship
            ),

        "percentage":
            check_percentage(
                student,
                scholarship
            ),

        "disability":
            check_disability(
                student,
                scholarship
            ),

        "minority":
            check_minority(
                student,
                scholarship
            ),

        "sports":
            check_sports(
                student,
                scholarship
            ),

        "exserviceman":
            check_exserviceman(
                student,
                scholarship
            )
    }


    satisfied = [
        key
        for key, value
        in conditions.items()
        if value == "satisfied"
    ]


    not_satisfied = [
        key
        for key, value
        in conditions.items()
        if value == "not_satisfied"
    ]


    unknown = [
        key
        for key, value
        in conditions.items()
        if value == "unknown"
    ]


    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    if not_satisfied:

        status = "not_eligible"

    elif unknown:

        status = "needs_verification"

    else:

        status = "eligible"


    return {

        "status": status,

        "conditions": conditions,

        "satisfied": satisfied,

        "not_satisfied": not_satisfied,

        "unknown": unknown

    }