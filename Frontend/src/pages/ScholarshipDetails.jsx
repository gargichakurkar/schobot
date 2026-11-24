import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getScholarship } from "../apiClient";
import Icon from "../components/Icon";

function externalUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function scholarshipFacts(scholarship) {
  const income = scholarship.income_text
    || (scholarship.max_income > 0
      ? `Up to ₹${Number(scholarship.max_income).toLocaleString("en-IN")}`
      : null);
  const facts = [
    ["Provider", scholarship.provider],
    ["Scholarship type", scholarship.scholarship_type],
    ["State / jurisdiction", scholarship.state],
    ["Category", scholarship.category],
    ["Income limit", income],
    ["Eligible education", scholarship.eligible_level || scholarship.qualification_text],
    ["Minimum marks", scholarship.minimum_marks_text],
    ["Gender requirement", scholarship.gender_requirement],
    ["Year stated in source", scholarship.year_text],
  ];
  return facts.filter(([, value]) => value);
}

export default function ScholarshipDetails() {
  const { id } = useParams();
  const [requestState, setRequestState] = useState(null);
  const isLoading = requestState?.id !== id || requestState.loading;
  const error = requestState?.id === id ? requestState.error : "";
  const scholarship = requestState?.id === id ? requestState.scholarship : null;

  useEffect(() => {
    let cancelled = false;
    getScholarship(id)
      .then((data) => {
        if (!cancelled) setRequestState({ id, loading: false, scholarship: data, error: "" });
      })
      .catch((requestError) => {
        if (!cancelled) {
          setRequestState({
            id,
            loading: false,
            scholarship: null,
            error: requestError.message || "Could not load scholarship details.",
          });
        }
      })
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (isLoading) {
    return <main className="content-page"><p role="status">Loading scholarship details...</p></main>;
  }

  if (!scholarship) {
    return (
      <main className="content-page">
        <div className="page-heading">
          <p className="eyebrow">SCHOBOT SCHOLARSHIP DIRECTORY</p>
          <h1>Scholarship details unavailable</h1>
          <p className="page-subtitle" role="alert">{error || "This scholarship could not be found."}</p>
        </div>
        <Link className="details-link details-back-link" to="/">Back to Available Scholarships</Link>
      </main>
    );
  }

  const facts = scholarshipFacts(scholarship);
  const applicationUrl = externalUrl(scholarship.official_link);
  const informationUrl = externalUrl(scholarship.scheme_info_link);

  return (
    <main className="content-page">
      <Link className="back-link" to="/">← Back to Available Scholarships</Link>
      <div className="details-title">
        <div className="details-title-main">
          <span className="scholarship-symbol"><Icon name="scholarship" size={22} /></span>
          <div>
            <div className="details-type-line">
              {scholarship.scholarship_type && (
                <span className={`type-badge ${scholarship.scholarship_type.toLowerCase()}`}>
                  {scholarship.scholarship_type}
                </span>
              )}
              <span className="directory-badge">SCHOLARSHIP DETAILS</span>
            </div>
            <h1>{scholarship.scholarship_name}</h1>
          </div>
        </div>
        <div className="scholarship-catalogue-links">
          {applicationUrl && (
            <a className="primary-button portal-button" href={applicationUrl} rel="noopener noreferrer" target="_blank">
              Official application portal <span aria-hidden="true">↗</span>
            </a>
          )}
          {informationUrl && (
            <a className="primary-button portal-button" href={informationUrl} rel="noopener noreferrer" target="_blank">
              Scheme information <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
      </div>

      <section className="details-card">
        <div className="details-section-title">
          <h2>Scholarship information</h2>
        </div>
        {facts.length > 0 && (
          <dl className="scholarship-facts">
            {facts.map(([label, value]) => (
              <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
            ))}
          </dl>
        )}
        {scholarship.description && (
          <div className="details-description">
            <h3>Description</h3>
            <p>{scholarship.description}</p>
          </div>
        )}
        {scholarship.benefits && (
          <div className="details-description">
            <h3>Benefits provided</h3>
            <p>{scholarship.benefits}</p>
          </div>
        )}
        {scholarship.required_documents && (
          <div className="details-description">
            <h3>Required documents</h3>
            <p>{scholarship.required_documents}</p>
          </div>
        )}
        {scholarship.additional_category_requirements && (
          <div className="details-description">
            <h3>Additional categories / communities</h3>
            <p>{scholarship.additional_category_requirements}</p>
          </div>
        )}
        {scholarship.eligibility_details && (
          <div className="details-description">
            <h3>Additional eligibility details</h3>
            <p>{scholarship.eligibility_details}</p>
          </div>
        )}
      </section>
    </main>
  );
}
