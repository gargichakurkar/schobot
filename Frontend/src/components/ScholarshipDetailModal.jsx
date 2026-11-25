import { useEffect, useState } from "react";
import {
  getScholarship,
  getScholarshipDocuments,
  getScholarshipEligibility,
  updateScholarshipDocument,
  uploadStudentDocument,
} from "../apiClient";
import ReminderPreferences from "./ReminderPreferences";
import { translate } from "../i18n";

function formatDeadline(value) {
  if (!value) return "TBD";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function officialWebsiteUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function awardAmount(scholarship) {
  if (scholarship.award_amount) return scholarship.award_amount;
  const text = scholarship.description || "";
  const match = text.match(/(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)/i);
  return match ? `₹${match[1]}` : "Not specified in this listing";
}

function formatIncome(scholarship) {
  if (scholarship.income_text) return scholarship.income_text;
  if (scholarship.max_income > 0) {
    return `Up to ₹${Number(scholarship.max_income).toLocaleString("en-IN")}`;
  }
  return "Not specified";
}

function formatUpdatedAt(value) {
  if (!value) return "Not updated yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : date.toLocaleString();
}

function renderStatusBadge(status) {
  switch (status) {
    case "verified":
      return <span className="doc-badge badge-verified">Verified ✓</span>;
    case "pending_review":
      return <span className="doc-badge badge-pending">Pending Review ⏳</span>;
    case "uploaded":
      return <span className="doc-badge badge-uploaded">Available in Vault 📁</span>;
    case "rejected":
      return <span className="doc-badge badge-rejected">Rejected ✕</span>;
    case "expired":
      return <span className="doc-badge badge-expired">Expired ⚠</span>;
    case "missing":
    default:
      return <span className="doc-badge badge-missing">Missing ✕</span>;
  }
}

export default function ScholarshipDetailModal({ recommendation, studentId, onClose }) {
  const [scholarship, setScholarship] = useState(null);
  const [checklistData, setChecklistData] = useState(null);
  const [isLoadingDetails, setIsLoadingDetails] = useState(true);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [detailsError, setDetailsError] = useState("");
  const [documentsError, setDocumentsError] = useState("");
  const [savingDocuments, setSavingDocuments] = useState({});
  const [documentErrors, setDocumentErrors] = useState({});
  const [savedDocuments, setSavedDocuments] = useState({});
  const [uploadingDoc, setUploadingDoc] = useState({});
  const [uploadErrors, setUploadErrors] = useState({});

  const [eligibility, setEligibility] = useState(() => {
    if (
      Array.isArray(recommendation?.passed_rules)
      || Array.isArray(recommendation?.failed_rules)
      || Array.isArray(recommendation?.unknown_rules)
    ) {
      return {
        match_status: recommendation.match_status,
        match_score: recommendation.match_score,
        passed_rules: recommendation.passed_rules || [],
        failed_rules: recommendation.failed_rules || [],
        unknown_rules: recommendation.unknown_rules || [],
        warnings: recommendation.warnings || [],
      };
    }
    return null;
  });
  const [isLoadingEligibility, setIsLoadingEligibility] = useState(false);
  const [eligibilityError, setEligibilityError] = useState("");

  const loadDocuments = () => {
    setIsLoadingDocuments(true);
    setDocumentsError("");
    return getScholarshipDocuments(studentId, recommendation.scholarship_id)
      .then((data) => {
        setChecklistData(data);
      })
      .catch((error) => {
        setDocumentsError(error.message || "Could not load the document checklist.");
      })
      .finally(() => {
        setIsLoadingDocuments(false);
      });
  };

  useEffect(() => {
    let cancelled = false;
    getScholarship(recommendation.scholarship_id)
      .then((data) => {
        if (!cancelled) setScholarship(data);
      })
      .catch((error) => {
        if (!cancelled) setDetailsError(error.message || "Could not load scholarship details.");
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDetails(false);
      });

    if (!eligibility && studentId && recommendation?.scholarship_id) {
      setIsLoadingEligibility(true);
      getScholarshipEligibility(recommendation.scholarship_id, studentId)
        .then((data) => {
          if (!cancelled) {
            setEligibility({
              match_status: data.match_status,
              match_score: data.match_score,
              passed_rules: data.passed_rules || [],
              failed_rules: data.failed_rules || [],
              unknown_rules: data.unknown_rules || [],
              warnings: data.warnings || [],
            });
          }
        })
        .catch((error) => {
          if (!cancelled) setEligibilityError(error.message || "Could not load eligibility evaluation.");
        })
        .finally(() => {
          if (!cancelled) setIsLoadingEligibility(false);
        });
    }

    loadDocuments();

    return () => {
      cancelled = true;
    };
  }, [recommendation.scholarship_id, studentId]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const saveDocumentNote = async (document, notes) => {
    setSavingDocuments((current) => ({ ...current, [document.document_name]: true }));
    setDocumentErrors((current) => ({ ...current, [document.document_name]: "" }));
    setSavedDocuments((current) => ({ ...current, [document.document_name]: false }));

    try {
      await updateScholarshipDocument(
        studentId,
        recommendation.scholarship_id,
        document.document_name,
        {
          status: document.status === "missing" ? "not_uploaded" : document.status,
          notes: notes || null,
        },
      );
      setChecklistData((current) => {
        if (!current) return current;
        return {
          ...current,
          documents: current.documents.map((item) =>
            item.document_name === document.document_name ? { ...item, notes } : item
          ),
        };
      });
      setSavedDocuments((current) => ({ ...current, [document.document_name]: true }));
    } catch (error) {
      setDocumentErrors((current) => ({
        ...current,
        [document.document_name]: error.message || "Failed to save note.",
      }));
    } finally {
      setSavingDocuments((current) => ({ ...current, [document.document_name]: false }));
    }
  };

  const handleInlineUpload = async (docReq, file) => {
    if (!file || !studentId) return;
    setUploadingDoc((prev) => ({ ...prev, [docReq.document_name]: true }));
    setUploadErrors((prev) => ({ ...prev, [docReq.document_name]: "" }));

    try {
      await uploadStudentDocument(
        studentId,
        docReq.standard_type || docReq.document_name,
        file,
        true,
      );
      // Auto-refresh checklist on successful upload
      await loadDocuments();
    } catch (err) {
      setUploadErrors((prev) => ({
        ...prev,
        [docReq.document_name]: err.message || "Upload failed. Please try again.",
      }));
    } finally {
      setUploadingDoc((prev) => ({ ...prev, [docReq.document_name]: false }));
    }
  };

  const detail = scholarship || {};
  const website = officialWebsiteUrl(detail.official_link || recommendation.official_link);
  const informationWebsite = officialWebsiteUrl(detail.scheme_info_link);
  const qualification = detail.eligible_level || detail.qualification_text || "Not specified";
  const course = detail.eligible_course || "Not specified";
  const deadline = detail.deadline || recommendation.deadline;
  const documents = checklistData?.documents || [];

  return (
    <div
      className="scholarship-modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
    >
      <section
        aria-labelledby="scholarship-modal-title"
        aria-modal="true"
        className="scholarship-detail-modal"
        role="dialog"
      >
        <header className="scholarship-modal-header">
          <div>
            <p className="eyebrow">SCHOLARSHIP DETAILS</p>
            <h2 id="scholarship-modal-title">
              {detail.scholarship_name || recommendation.scholarship_name || "Scholarship"}
            </h2>
          </div>
          <button aria-label="Close scholarship details" className="modal-close-button" onClick={onClose} type="button">
            Close
          </button>
        </header>

        {detailsError && <p className="modal-error" role="alert">{detailsError}</p>}
        {isLoadingDetails ? (
          <p role="status">Loading scholarship details...</p>
        ) : (
          <>
            <dl className="scholarship-detail-facts">
              <div><dt>Award amount</dt><dd>{awardAmount(detail)}</dd></div>
              <div><dt>{translate("en", "deadlineLabel")}</dt><dd>{formatDeadline(deadline)}</dd></div>
              <div><dt>Eligible education</dt><dd>{qualification}</dd></div>
              <div><dt>Eligible course</dt><dd>{course}</dd></div>
              <div><dt>Provider</dt><dd>{detail.provider || "Not specified"}</dd></div>
              <div><dt>Category</dt><dd>{detail.category || "Not specified"}</dd></div>
              <div><dt>Income criteria</dt><dd>{formatIncome(detail)}</dd></div>
              {detail.minimum_marks_text && <div><dt>Minimum marks</dt><dd>{detail.minimum_marks_text}</dd></div>}
              {detail.gender_requirement && <div><dt>Gender requirement</dt><dd>{detail.gender_requirement}</dd></div>}
            </dl>
            {Array.isArray(detail.milestones) && detail.milestones.length > 0 && (
              <section className="scholarship-milestones">
                <h3>{translate("en", "milestonesTitle")}</h3>
                <ul>
                  {detail.milestones.map((milestone, index) => (
                    <li key={`${milestone.label || milestone.milestone_type || "milestone"}-${index}`}>
                      <strong>{milestone.label || milestone.milestone_type || "Milestone"}</strong>
                      <span>{formatDeadline(milestone.date)}</span>
                      {milestone.description ? <small>{milestone.description}</small> : null}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {detail.description && <p className="scholarship-modal-description">{detail.description}</p>}
            {detail.benefits && <p className="scholarship-modal-description"><strong>Benefits:</strong> {detail.benefits}</p>}
            {detail.required_documents && (
              <p className="scholarship-modal-description">
                <strong>Official requirement text:</strong> {detail.required_documents}
              </p>
            )}
            {detail.eligibility_details && (
              <p className="scholarship-modal-description">
                <strong>Additional eligibility details:</strong> {detail.eligibility_details}
              </p>
            )}
            {website ? (
              <a className="primary-button scholarship-modal-website" href={website} rel="noopener noreferrer" target="_blank">
                Apply now
              </a>
            ) : (
              <p className="modal-muted">No official website is listed for this scholarship.</p>
            )}
            {informationWebsite && (
              <a className="details-link" href={informationWebsite} rel="noopener noreferrer" target="_blank">
                Read scheme information
              </a>
            )}
          </>
        )}

        <section className="eligibility-explanation-section">
          <h3>Why You Match This Scholarship</h3>

          {isLoadingEligibility ? (
            <p role="status">Loading eligibility breakdown...</p>
          ) : eligibilityError ? (
            <p className="modal-error" role="alert">{eligibilityError}</p>
          ) : eligibility ? (
            <>
              <div className={`eligibility-status-banner status-${eligibility.match_status || "unknown"}`}>
                <span>
                  Eligibility Status:{" "}
                  <strong>
                    {eligibility.match_status === "likely_eligible"
                      ? "Likely Eligible"
                      : eligibility.match_status === "needs_verification"
                        ? "Needs Verification"
                        : eligibility.match_status === "not_matched"
                          ? "Not Eligible"
                          : eligibility.match_status?.replaceAll("_", " ") || "Under Evaluation"}
                  </strong>
                </span>
                {eligibility.match_score != null && (
                  <span>
                    Match Score: <strong>{Math.round(eligibility.match_score)}%</strong>
                  </span>
                )}
              </div>

              <div className="explanation-groups">
                {/* Group A: Requirements you meet */}
                <div className="explanation-group group-passed">
                  <h4>
                    <span aria-hidden="true">✓</span> Requirements you meet
                    {eligibility.passed_rules?.length ? ` (${eligibility.passed_rules.length})` : ""}
                  </h4>
                  {eligibility.passed_rules?.length > 0 ? (
                    <ul>
                      {eligibility.passed_rules.map((rule, index) => (
                        <li key={`passed-${rule.field || index}`}>
                          <strong>{rule.label}:</strong> {rule.message}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="explanation-empty">No criteria currently marked as passed.</p>
                  )}
                </div>

                {/* Group B: Requirements you do not meet */}
                <div className="explanation-group group-failed">
                  <h4>
                    <span aria-hidden="true">✕</span> Requirements you do not meet
                    {eligibility.failed_rules?.length ? ` (${eligibility.failed_rules.length})` : ""}
                  </h4>
                  {eligibility.failed_rules?.length > 0 ? (
                    <ul>
                      {eligibility.failed_rules.map((rule, index) => (
                        <li key={`failed-${rule.field || index}`}>
                          <strong>{rule.label}:</strong> {rule.message}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="explanation-empty">None — no disqualifying conditions identified.</p>
                  )}
                </div>

                {/* Group C: Needs verification */}
                <div className="explanation-group group-unknown">
                  <h4>
                    <span aria-hidden="true">⚠</span> Needs verification
                    {eligibility.unknown_rules?.length ? ` (${eligibility.unknown_rules.length})` : ""}
                  </h4>
                  <p className="explanation-guidance">
                    These conditions require additional documentation or cannot be confirmed from your current profile.
                  </p>
                  {eligibility.unknown_rules?.length > 0 ? (
                    <ul>
                      {eligibility.unknown_rules.map((rule, index) => (
                        <li key={`unknown-${rule.field || index}`}>
                          <strong>{rule.label}:</strong> {rule.message}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="explanation-empty">None — all criteria have been verified against your profile.</p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <p className="modal-muted">Complete and save your profile to see detailed eligibility matching.</p>
          )}
        </section>

        <ReminderPreferences studentId={studentId} scholarshipId={recommendation.scholarship_id} />

        {/* Dynamic Required Documents & Vault Matching Section */}
        <section className="document-checklist">
          <div className="document-section-header">
            <h3>Required Documents Checklist</h3>
            <span className="vault-reuse-indicator">Cross-Scholarship Vault Active ⚡</span>
          </div>

          <p className="document-help">
            Requirements are specific to this scholarship scheme. Documents uploaded once into your Document Vault
            are automatically matched and reused across all scholarships.
          </p>

          {/* Missing Documents Summary Box */}
          {checklistData && (
            <div className="document-summary-box">
              <div className="summary-stat">
                <span>Total Required</span>
                <strong>{checklistData.required_count}</strong>
              </div>
              <div className="summary-stat stat-available">
                <span>Available in Vault</span>
                <strong>{checklistData.available_count}</strong>
              </div>
              <div className="summary-stat stat-missing">
                <span>Missing Documents</span>
                <strong>{checklistData.missing_count}</strong>
              </div>
              <div className="summary-message">
                {checklistData.missing_count === 0 ? (
                  <span className="ready-text">✓ All required documents are available in your vault!</span>
                ) : (
                  <span>
                    <strong>{checklistData.missing_count}</strong> document
                    {checklistData.missing_count > 1 ? "s" : ""} missing from your vault. Upload below to complete your application.
                  </span>
                )}
              </div>
            </div>
          )}

          {documentsError && <p className="modal-error" role="alert">{documentsError}</p>}

          {isLoadingDocuments ? (
            <p role="status">Evaluating document requirements against your vault...</p>
          ) : documents.length > 0 ? (
            <div className="document-checklist-items">
              {documents.map((document) => (
                <article className="document-checklist-item" key={document.document_name}>
                  <div className="document-info-cell">
                    <strong className="document-name-text">{document.document_name}</strong>
                    <span className="document-type-tag">{document.standard_type}</span>
                    {document.matched_document_filename && (
                      <span className="vault-matched-file">
                        📁 Reused from vault: <em>{document.matched_document_filename}</em>
                      </span>
                    )}
                  </div>

                  <div className="document-status-cell">
                    {renderStatusBadge(document.status)}

                    {/* Inline Upload Option for Missing Documents */}
                    {(document.status === "missing" || document.status === "rejected" || document.status === "expired") && (
                      <div className="document-upload-action">
                        <label className="vault-upload-btn">
                          {uploadingDoc[document.document_name] ? "Uploading..." : "Upload to Vault"}
                          <input
                            accept=".pdf,.jpg,.jpeg,.png"
                            disabled={Boolean(uploadingDoc[document.document_name])}
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) handleInlineUpload(document, file);
                            }}
                            type="file"
                          />
                        </label>
                      </div>
                    )}
                    {uploadErrors[document.document_name] && (
                      <small className="field-error-text">{uploadErrors[document.document_name]}</small>
                    )}
                  </div>

                  <div className="document-note-cell">
                    <label className="document-note-field">
                      <span>Note (optional)</span>
                      <textarea
                        disabled={Boolean(savingDocuments[document.document_name])}
                        onBlur={(event) => {
                          if (event.target.value !== (document.notes || "")) {
                            saveDocumentNote(document, event.target.value);
                          }
                        }}
                        defaultValue={document.notes || ""}
                        placeholder="Add a reference note"
                        rows="2"
                      />
                    </label>
                  </div>

                  <small className="document-save-state" role="status">
                    {savingDocuments[document.document_name]
                      ? "Saving note..."
                      : documentErrors[document.document_name]
                        ? documentErrors[document.document_name]
                        : savedDocuments[document.document_name]
                          ? "Saved"
                          : document.updated_at
                            ? `Last updated: ${formatUpdatedAt(document.updated_at)}`
                            : ""}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p className="modal-muted">No specific documents are required for this scholarship.</p>
          )}

          <div className="verification-warning-notice">
            <small>
              <strong>Verification policy:</strong> Uploaded documents undergo administrative review before being marked
              as verified. Scanning a certificate or uploading a file confirms availability in your vault, but does not
              substitute for verification by scholarship authorities.
            </small>
          </div>
        </section>
      </section>
    </div>
  );
}
