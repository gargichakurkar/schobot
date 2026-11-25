export const initialProfile = {
  full_name: "",
  email: "",
  phone_number: "",
  date_of_birth: "",
  education_level: "",
  course: "",
  study_year: "",
  college_name: "",
  state: "",
  category: "",
  annual_family_income: "",
  gender: "",
  academic_score: "",
  score_type: "",
  disability_percentage: "",
  has_valid_disability_certificate: null,
  has_udid: null,
  has_disability_certificate: null,
  is_orphan: null,
  parent_death_due_to_covid: null,
  parent_martyred_armed_forces: null,
  is_dependent_of_rpf_rpsf: null,
  parent_service_category: "",
  previous_year_passed: null,
  receives_other_scholarship: null,
  has_income_certificate: null,
};

export const educationLevels = [
  "Class 9",
  "Class 10",
  "Class 11",
  "Class 12",
  "Diploma",
  "Undergraduate",
  "Postgraduate",
];

export const categories = ["General", "OBC", "SC/ST", "VJNT", "PWD"];

export const educationLevelsProfile = [
  "Class 9",
  "Class 10",
  "Class 11",
  "Class 12",
  "Diploma",
  "Graduation",
  "Undergraduate",
  "Postgraduate",
];

export const categoriesProfile = [
  "General",
  "OBC",
  "SC",
  "ST",
  "SC/ST",
  "EWS",
  "SEBC",
  "VJNT",
  "PWD",
  "Minority",
  "Other",
];

const storageKey = "schobot-student-profile";
const studentIdKey = "schobot_student_id";

function hasText(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function normalizeEducationLevel(value) {
  if (typeof value !== "string") return value;
  const normalized = value.trim().toLowerCase();
  const aliases = {
    "under graduate": "Undergraduate",
    graduation: "Graduation",
    "class 9": "Class 9",
    "class 10": "Class 10",
    "class 11": "Class 11",
    "class 12": "Class 12",
    diploma: "Diploma",
    undergraduate: "Undergraduate",
    postgraduate: "Postgraduate",
  };
  return aliases[normalized] || "";
}

export function normalizeCategory(value) {
  if (typeof value !== "string") return "";
  const normalized = value.trim().toLowerCase();
  const aliases = {
    general: "General",
    obc: "OBC",
    sebc: "SEBC",
    sc: "SC",
    st: "ST",
    "sc/st": "SC/ST",
    vjnt: "VJNT",
    pwd: "PWD",
    ews: "EWS",
    minority: "Minority",
    other: "Other",
  };
  return aliases[normalized] || "";
}

export function normalizeStudentProfile(profile) {
  return {
    ...profile,
    education_level: normalizeEducationLevel(profile.education_level),
    category: normalizeCategory(profile.category),
  };
}

export function isStudentProfileComplete(profile) {
  const educationLevel = normalizeEducationLevel(profile.education_level || profile.educationLevel);
  const course = profile.course;
  const state = profile.state;
  const category = normalizeCategory(profile.category);
  const rawIncome = profile.annual_family_income ?? profile.annualFamilyIncome;
  const income = Number(String(rawIncome ?? "").replace(/[₹,\s]/g, ""));

  return Boolean(
    educationLevelsProfile.includes(educationLevel)
    && hasText(course)
    && hasText(state)
    && categoriesProfile.includes(category)
    && Number.isFinite(income)
    && income > 0
  );
}

export function getStudentName() {
  const saved = window.localStorage.getItem(storageKey);
  if (!saved) return null;

  try {
    const profile = JSON.parse(saved);
    const name = profile.full_name || profile.fullName;
    return typeof name === "string" && name.trim() ? name.trim() : null;
  } catch (error) {
    console.error("Could not read the saved Schobot profile name.", error);
    return null;
  }
}

export function loadStudentProfile() {
  const saved = window.localStorage.getItem(storageKey);
  if (!saved) return { ...initialProfile };

  try {
    return normalizeStudentProfile({ ...initialProfile, ...JSON.parse(saved) });
  } catch (error) {
    console.error("Could not read the saved Schobot profile.", error);
    return { ...initialProfile };
  }
}

export function saveStudentProfile(profile) {
  window.localStorage.setItem(storageKey, JSON.stringify(normalizeStudentProfile(profile)));
}

export function getStudentId() {
  return window.localStorage.getItem(studentIdKey);
}

export function saveStudentId(studentId) {
  window.localStorage.setItem(studentIdKey, studentId);
}

export function clearStudentId() {
  window.localStorage.removeItem(studentIdKey);
}

export function profileFromBackend(serverProfile, localProfile = initialProfile) {
  return {
    ...localProfile,
    full_name: serverProfile.full_name || localProfile.full_name,
    email: serverProfile.email || localProfile.email,
    education_level: normalizeEducationLevel(
      serverProfile.education_level || localProfile.education_level,
    ),
    course: serverProfile.course || localProfile.course,
    study_year: serverProfile.study_year || localProfile.study_year,
    college_name: serverProfile.college_name || localProfile.college_name,
    academic_score: serverProfile.academic_score == null
      ? localProfile.academic_score
      : String(serverProfile.academic_score),
    score_type: serverProfile.score_type || localProfile.score_type,
    state: serverProfile.domicile_state || serverProfile.study_state || localProfile.state,
    category: normalizeCategory(serverProfile.category || localProfile.category),
    gender: serverProfile.gender || localProfile.gender,
    annual_family_income: serverProfile.annual_family_income == null
      ? localProfile.annual_family_income
      : String(serverProfile.annual_family_income),
    disability_percentage: serverProfile.disability_percentage == null
      ? localProfile.disability_percentage
      : String(serverProfile.disability_percentage),
    has_valid_disability_certificate: serverProfile.has_valid_disability_certificate ?? localProfile.has_valid_disability_certificate,
    has_udid: serverProfile.has_udid ?? localProfile.has_udid,
    has_disability_certificate: serverProfile.has_disability_certificate ?? localProfile.has_disability_certificate,
    is_orphan: serverProfile.is_orphan ?? localProfile.is_orphan,
    parent_death_due_to_covid: serverProfile.parent_death_due_to_covid ?? localProfile.parent_death_due_to_covid,
    parent_martyred_armed_forces: serverProfile.parent_martyred_armed_forces ?? localProfile.parent_martyred_armed_forces,
    is_dependent_of_rpf_rpsf: serverProfile.is_dependent_of_rpf_rpsf ?? localProfile.is_dependent_of_rpf_rpsf,
    parent_service_category: serverProfile.parent_service_category || localProfile.parent_service_category,
    previous_year_passed: serverProfile.previous_year_passed ?? localProfile.previous_year_passed,
    receives_other_scholarship: serverProfile.receives_other_scholarship ?? localProfile.receives_other_scholarship,
    has_income_certificate: serverProfile.has_income_certificate ?? localProfile.has_income_certificate,
  };
}
