import { useEffect, useState } from "react";
import {
  getScholarship,
  getScholarshipDocuments,
  updateScholarshipDocument,
} from "../apiClient";
import ReminderPreferences from "./ReminderPreferences";
import { translate } from "../i18n";

const documentStatuses = [
  { value: "not_uploaded", label: "Not uploaded" },
  { value: "uploaded", label: "Uploaded" },
  { value: "verified", label: "Verified" },
];

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

export default function ScholarshipDetailModal({ recommendation, studentId, onClose }) {
  const [scholarship, setScholarship] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [isLoadingDetails, setIsLoadingDetails] = useState(true);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [detailsError, setDetailsError] = useState("");
  const [documentsError, setDocumentsError] = useState("");
  const [savingDocuments, setSavingDocuments] = useState({});
  const [documentErrors, setDocumentErrors] = useState({});
  const [savedDocuments, setSavedDocuments] = useState({});

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

    getScholarshipDocuments(studentId, recommendation.scholarship_id)
      .then((data) => {
        if (!cancelled) {
          if (!Array.isArray(data.documents)) {
            throw new Error("The server returned an invalid document checklist.");
          }
          setDocuments(data.documents);
        }
      })
      .catch((error) => {
        if (!cancelled) setDocumentsError(error.message || "Could not load the document checklist.");
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDocuments(false);
      });

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

  const saveDocument = async (document, changes) => {
    const updatedDocument = { ...document, ...changes };
    setDocuments((current) => current.map((item) => (
      item.document_name === document.document_name ? updatedDocument : item
    )));
    setSavingDocuments((current) => ({ ...current, [document.document_name]: true }));
    setDocumentErrors((current) => ({ ...current, [document.document_name]: "" }));
    setSavedDocuments((current) => ({ ...current, [document.document_name]: false }));

    try {
      const savedDocument = await updateScholarshipDocument(
        studentId,
        recommendation.scholarship_id,
        document.document_name,
        {
          status: updatedDocument.status,
          notes: updatedDocument.notes || null,
        },
      );
      setDocuments((current) => current.map((item) => (
        item.document_name === document.document_name ? savedDocument : item
      )));
      setSavedDocuments((current) => ({ ...current, [document.document_name]: true }));
    } catch (error) {
      setDocuments((current) => current.map((item) => (
        item.document_name === document.document_name ? document : item
      )));
      setDocumentErrors((current) => ({
        ...current,
        [document.document_name]: error.message || "Failed to save; please try again.",
      }));
    } finally {
      setSavingDocuments((current) => ({ ...current, [document.document_name]: false }));
    }
  };

  const detail = scholarship || {};
  const website = officialWebsiteUrl(detail.official_link || recommendation.official_link);
  const informationWebsite = officialWebsiteUrl(detail.scheme_info_link);
  const qualification = detail.eligible_level || detail.qualification_text || "Not specified";
  const course = detail.eligible_course || "Not specified";
  const deadline = detail.deadline || recommendation.deadline;

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
            {detail.required_documents && <p className="scholarship-modal-description"><strong>Required documents:</strong> {detail.required_documents}</p>}
            {detail.eligibility_details && <p className="scholarship-modal-description"><strong>Additional eligibility details:</strong> {detail.eligibility_details}</p>}
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

        <ReminderPreferences studentId={studentId} scholarshipId={recommendation.scholarship_id} />

        <section className="document-checklist">
          <h3>Document verification</h3>
          <p className="document-help">
            Mark each document’s status. “Verified” means the documents have been checked by the scholarship authority.
            This common checklist may not include every scheme-specific requirement; confirm the list on the official website.
          </p>
          {documentsError && <p className="modal-error" role="alert">{documentsError}</p>}
          {isLoadingDocuments ? (
            <p role="status">Loading document checklist...</p>
          ) : documents.length > 0 ? (
            <div className="document-checklist-items">
              {documents.map((document) => (
                <article className="document-checklist-item" key={document.document_name}>
                  <strong>{document.document_name}</strong>
                  <label>
                    <span>Status</span>
                    <select
                      aria-label={`${document.document_name} status`}
                      disabled={Boolean(savingDocuments[document.document_name])}
                      onChange={(event) => saveDocument(document, { status: event.target.value })}
                      value={document.status}
                    >
                      {documentStatuses.map((status) => (
                        <option key={status.value} value={status.value}>{status.label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="document-note-field">
                    <span>Note (optional)</span>
                    <textarea
                      disabled={Boolean(savingDocuments[document.document_name])}
                      onBlur={(event) => {
                        if (event.target.value !== (document.notes || "")) {
                          saveDocument(document, { notes: event.target.value });
                        }
                      }}
                      onChange={(event) => setDocuments((current) => current.map((item) => (
                        item.document_name === document.document_name
                          ? { ...item, notes: event.target.value }
                          : item
                      )))}
                      placeholder="Add a note"
                      rows="2"
                      value={document.notes || ""}
                    />
                  </label>
                  <small className="document-save-state" role="status">
                    {savingDocuments[document.document_name]
                      ? "Saving..."
                      : documentErrors[document.document_name]
                        ? documentErrors[document.document_name]
                        : savedDocuments[document.document_name]
                          ? `Saved · Last updated: ${formatUpdatedAt(document.updated_at)}`
                          : `Last updated: ${formatUpdatedAt(document.updated_at)}`}
                  </small>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      </section>
    </div>
  );
}
