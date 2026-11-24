import { useEffect, useMemo, useState } from "react";
import Icon from "../components/Icon";
import ScholarshipCard from "../components/ScholarshipCard";
import { getScholarships } from "../apiClient";
import { educationLevels, getStudentName } from "../data/profile";
import { dedupeByScholarshipId } from "../data/scholarships";

function educationLevelsForScholarship(scholarship) {
  const qualification = String(
    scholarship.qualification_text
      || scholarship.eligible_level
      || scholarship.educationLevel
      || "",
  )
    .toLowerCase()
    .replace(/[–—]/g, "-")
    .replace(/\bgrduat|\bgradutat/g, "graduat")
    .replace(/\b10\s+th\b/g, "10th")
    .replace(/\b11\s+th\b/g, "11th")
    .replace(/\b12\s+th\b/g, "12th");
  const levels = new Set();

  if (/all students|all levels|any education|all education/.test(qualification)) {
    return new Set(educationLevels);
  }
  if (/1st\s+to\s+10th|class\s*1\s+to\s+class\s*10|classes?\s*9|9th|ninth/.test(qualification)) {
    levels.add("Class 9");
  }
  if (/1st\s+to\s+10th|class\s*1\s+to\s+class\s*10|classes?\s*10|10th|ssc|secondary/.test(qualification)) {
    levels.add("Class 10");
  }
  if (/classes?\s*11\s*-\s*12|classes?\s*11\s*(and|&|or)\s*12|11th\s*(and|&|or)\s*12th/.test(qualification)) {
    levels.add("Class 11");
    levels.add("Class 12");
  } else {
    if (/classes?\s*11|11th|fyjc|syjc/.test(qualification)) levels.add("Class 11");
    if (/classes?\s*12|12th|hsc|senior/.test(qualification)) levels.add("Class 12");
  }
  if (/diploma|11th\s+or\s+above|classes?\s*11\s+and\s+above|post.?matric/.test(qualification)) {
    levels.add("Class 11");
    levels.add("Undergraduate");
    levels.add("Diploma");
  }
  if (/under.?grad|gr?aduat(?:ion)?|bachelor|degree|b\.?tech|m\.?b\.?b\.?s|b\.?sc/.test(qualification)) {
    levels.add("Undergraduate");
  }
  if (/post.?grad|master|ph\.?d|doctor|m\.?tech|m\.?e\.|m\.?s\.|m\.?b\.?a|d\.?m\.|under\/post|11th\s+or\s+above|classes?\s*11\s+and\s+above|post.?matric/.test(qualification)) {
    levels.add("Postgraduate");
  }
  if (/11th\s+or\s+above|classes?\s*11\s+and\s+above|post.?matric/.test(qualification)) {
    levels.add("Class 12");
  }
  if (/class 1 to class 10/.test(qualification)) {
    levels.add("Class 9");
    levels.add("Class 10");
  }

  return levels;
}

function scholarshipMatchesCategory(scholarshipCategory, selectedCategory) {
  const category = String(scholarshipCategory || "").trim().toLowerCase();
  const selected = String(selectedCategory || "").trim().toLowerCase();
  if (["all", "all categories", "any", "any category"].includes(selected)) {
    return ["all", "all categories", "any", "any category"].includes(category);
  }
  if (category === selected) return true;
  if (["all", "all categories", "any", "any category"].includes(category)) return true;

  const categoriesInListing = category
    .split(/[,;|/]|(?:\s+or\s+)|(?:\s+and\s+)|&/i)
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  const aliases = {
    "SC/ST": ["sc", "st", "sc/st"],
    OBC: ["obc", "sebc"],
    VJNT: ["vjnt", "vj", "nt", "ntdnt", "dnt", "sbc"],
    PWD: ["pwd"],
    General: ["general", "open"],
  };
  const matchingCategories = aliases[selectedCategory] || [selected];
  return matchingCategories.some((value) => categoriesInListing.includes(value));
}

function scholarshipMatchesState(scholarshipState, selectedState) {
  const state = String(scholarshipState || "").trim().toLowerCase();
  const selected = String(selectedState || "").trim().toLowerCase();
  return state === "all india" || state === selected;
}

function scholarshipForCatalogue(record) {
  const income = record.income_text
    || (record.max_income > 0
      ? `Up to ₹${Number(record.max_income).toLocaleString("en-IN")}`
      : "Not specified");
  return {
    ...record,
    name: record.scholarship_name,
    provider: record.provider || "Provider not specified",
    state: record.state || "Jurisdiction not specified",
    category: record.category || "Not specified",
    educationLevel: record.eligible_level || record.qualification_text || "Not specified",
    type: record.scholarship_type || "Not specified",
    income,
    description: record.description || "Description not provided in this dataset.",
    benefits: record.benefits || "Not specified",
    requiredDocuments: record.required_documents || "Not specified",
    eligibilityDetails: record.eligibility_details,
    officialLink: record.official_link,
    schemeInfoLink: record.scheme_info_link,
  };
}

const currentDate = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  month: "long",
  day: "numeric",
  year: "numeric",
}).format(new Date()).toUpperCase();

export default function AvailableScholarships() {
  const [studentName, setStudentName] = useState(getStudentName);
  const [scholarships, setScholarships] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [educationFilter, setEducationFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    getScholarships()
      .then((records) => {
        if (!Array.isArray(records)) {
          throw new Error("The server returned an invalid scholarship catalogue.");
        }
        if (!cancelled) {
          setScholarships(dedupeByScholarshipId(records).map(scholarshipForCatalogue));
        }
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message || "Could not load scholarships.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const updateStudentName = () => setStudentName(getStudentName());
    window.addEventListener("schobot-profile-updated", updateStudentName);
    window.addEventListener("storage", updateStudentName);
    return () => {
      window.removeEventListener("schobot-profile-updated", updateStudentName);
      window.removeEventListener("storage", updateStudentName);
    };
  }, []);

  const stateOptions = useMemo(
    () => [...new Set(scholarships.map((item) => item.state))].sort(),
    [scholarships],
  );
  const categoryOptions = useMemo(
    () => [...new Set(scholarships.map((item) => item.category))].sort(),
    [scholarships],
  );
  const typeOptions = useMemo(
    () => [...new Set(scholarships.map((item) => item.type))].sort(),
    [scholarships],
  );

  const displayedScholarships = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return scholarships.filter((scholarship) => (
      (!normalizedQuery || [
        scholarship.name,
        scholarship.provider,
        scholarship.description,
        scholarship.benefits,
        scholarship.requiredDocuments,
        scholarship.state,
        scholarship.category,
      ].join(" ").toLowerCase().includes(normalizedQuery))
      && (!stateFilter || scholarshipMatchesState(scholarship.state, stateFilter))
      && (!categoryFilter || scholarshipMatchesCategory(scholarship.category, categoryFilter))
      && (!educationFilter || educationLevelsForScholarship(scholarship).has(educationFilter))
      && (!typeFilter || scholarship.type === typeFilter)
    ));
  }, [categoryFilter, educationFilter, query, scholarships, stateFilter, typeFilter]);

  return (
    <main className="content-page">
      <div className="welcome-line">
        <div>
          <p className="eyebrow">{currentDate}</p>
          <h1>Hello {studentName || "Student"}! <span aria-hidden="true">👋</span></h1>
          <p className="page-subtitle">Explore scholarships available for students.</p>
        </div>
      </div>

      <section className="list-section">
        <div className="list-heading">
          <div>
            <p className="section-kicker">EXPLORE THE DIRECTORY</p>
            <h2>Available Scholarships</h2>
            <p>Explore scholarships available for students.</p>
          </div>
          <span className="result-count">Showing {displayedScholarships.length} scholarships</span>
        </div>

        <div className="filter-panel">
          <label className="search-field">
            <Icon name="search" size={19} />
            <input
              aria-label="Search scholarships"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search scholarships..."
              type="search"
              value={query}
            />
          </label>
          <label className="filter-field">
            <span>State</span>
            <select aria-label="Filter by state" onChange={(event) => setStateFilter(event.target.value)} value={stateFilter}>
              <option value="">All states</option>
              {stateOptions.map((state) => <option key={state} value={state}>{state}</option>)}
            </select>
          </label>
          <label className="filter-field">
            <span>Category</span>
            <select aria-label="Filter by category" onChange={(event) => setCategoryFilter(event.target.value)} value={categoryFilter}>
              <option value="">All categories</option>
              {categoryOptions.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
          </label>
          <label className="filter-field">
            <span>Education level</span>
            <select aria-label="Filter by education level" onChange={(event) => setEducationFilter(event.target.value)} value={educationFilter}>
              <option value="">All education levels</option>
              {educationLevels.map((level) => <option key={level} value={level}>{level}</option>)}
            </select>
          </label>
          <label className="filter-field">
            <span>Type</span>
            <select aria-label="Filter by scholarship type" onChange={(event) => setTypeFilter(event.target.value)} value={typeFilter}>
              <option value="">All types</option>
              {typeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
          </label>
        </div>

        {isLoading && <p className="api-feedback" role="status">Loading scholarships from Schobot...</p>}
        {loadError && <p className="api-feedback api-feedback-error" role="alert">{loadError}</p>}
        {!isLoading && !loadError && (
          <div className="scholarship-list">
            {displayedScholarships.map((scholarship) => (
              <ScholarshipCard key={scholarship.id} scholarship={scholarship} />
            ))}
            {displayedScholarships.length === 0 && (
              <div className="empty-state">
                <Icon name="filter" size={24} />
                <strong>No scholarships match these filters</strong>
                <span>Try another search or clear one of the filters.</span>
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
