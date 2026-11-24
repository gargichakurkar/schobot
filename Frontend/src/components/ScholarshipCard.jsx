import { Link } from "react-router-dom";
import Icon from "./Icon";

function externalUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export default function ScholarshipCard({ scholarship }) {
  const applicationUrl = externalUrl(scholarship.officialLink);
  const informationUrl = externalUrl(scholarship.schemeInfoLink);

  return (
    <article className="scholarship-row">
      <span className="scholarship-symbol"><Icon name="scholarship" size={20} /></span>
      <div className="scholarship-main">
        <div className="scholarship-title-line">
          <h2>{scholarship.name}</h2>
          <span className={`type-badge ${scholarship.type.toLowerCase().replace(/\s+/g, "-")}`}>
            {scholarship.type}
          </span>
        </div>
        <div className="scholarship-meta">
          <span>{scholarship.provider}</span>
          <i />
          <span>{scholarship.state}</span>
          <i />
          <span>{scholarship.category}</span>
          <i />
          <span>{scholarship.educationLevel}</span>
        </div>
        <p className="scholarship-description">{scholarship.description}</p>
        <div className="scholarship-catalogue-details">
          <p><strong>Education:</strong> {scholarship.educationLevel}</p>
          <p><strong>Benefits:</strong> {scholarship.benefits}</p>
          <p><strong>Required documents:</strong> {scholarship.requiredDocuments}</p>
          {scholarship.eligibilityDetails && (
            <p><strong>Additional eligibility:</strong> {scholarship.eligibilityDetails}</p>
          )}
        </div>
        {(applicationUrl || informationUrl) && (
          <div className="scholarship-catalogue-links">
            {applicationUrl && (
              <a href={applicationUrl} rel="noopener noreferrer" target="_blank">
                Official application portal
              </a>
            )}
            {informationUrl && (
              <a href={informationUrl} rel="noopener noreferrer" target="_blank">
                Scheme information
              </a>
            )}
          </div>
        )}
      </div>
      <div className="scholarship-value">
        <span>Income limit</span>
        <strong>{scholarship.income}</strong>
      </div>
      <Link className="details-link" to={`/scholarship/${encodeURIComponent(scholarship.id)}`}>
        View Details <Icon name="chevron" size={15} />
      </Link>
    </article>
  );
}
