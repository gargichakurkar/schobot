import { isStudentProfileComplete } from "./profile";

function normalize(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function educationRank(value) {
  const level = normalize(value);
  if (/postgraduate|post graduation|post grad|master|phd|doctor/.test(level)) return 4;
  if (/graduation|graduate|undergraduate|bachelor/.test(level)) return 3;
  if (/diploma|class 12|12th|hsc|senior|fyjc|syjc/.test(level)) return 2;
  if (/class 10|10th|ssc|secondary/.test(level)) return 1;
  return null;
}

function incomeNumber(value) {
  const digits = String(value ?? "").replace(/[^\d.]/g, "");
  const income = Number(digits);
  return Number.isFinite(income) && income > 0 ? income : null;
}

function matchesCategory(scholarshipCategory, studentCategory) {
  const accepted = normalize(scholarshipCategory);
  if (["all", "all categories", "general"].includes(accepted)) return true;

  return String(scholarshipCategory || "")
    .split(/[/,]| or /i)
    .map(normalize)
    .includes(normalize(studentCategory));
}

function matchesCourse(requiredCourse, studentCourse) {
  if (!requiredCourse || normalize(requiredCourse) === "not specified") return true;

  const required = normalize(requiredCourse);
  const course = normalize(studentCourse);
  if (/recognized undergraduate|eligible undergraduate|any course|all courses/.test(required)) return true;

  return required.includes(course) || course.includes(required);
}

export function computeEligibleScholarships(profile, scholarshipList) {
  if (!isStudentProfileComplete(profile)) return [];

  const studentState = normalize(profile.state || profile.domicile_state);
  const studentCategory = profile.category;
  const studentEducation = educationRank(profile.education_level || profile.educationLevel);
  const studentIncome = incomeNumber(profile.annual_family_income ?? profile.annualFamilyIncome);
  const studentCourse = profile.course;

  return scholarshipList.filter((scholarship) => {
    const scholarshipState = normalize(scholarship.state);
    const stateMatches = scholarshipState === "all india" || scholarshipState === studentState;
    const categoryMatches = matchesCategory(scholarship.category, studentCategory);
    const requiredEducation = educationRank(scholarship.qualification || scholarship.educationLevel);
    const educationMatches = requiredEducation !== null
      && studentEducation !== null
      && studentEducation >= requiredEducation;

    const maximumIncome = incomeNumber(
      scholarship.max_income ?? scholarship.maxIncome ?? scholarship.income,
    );
    const incomeMatches = maximumIncome === null || studentIncome <= maximumIncome;

    return stateMatches
      && categoryMatches
      && educationMatches
      && incomeMatches
      && matchesCourse(scholarship.course, studentCourse);
  });
}
