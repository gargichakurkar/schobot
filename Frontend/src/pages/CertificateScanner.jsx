import { useEffect, useState } from "react";
import {
  deleteStudentDocument,
  getStudentDocuments,
  scanCertificateDocument,
  uploadStudentDocument,
} from "../apiClient";
import { getAuthToken, getStudentId, isAuthenticated } from "../data/profile";
import "./CertificateScanner.css";

const certificateTypes = [
  { value: "income_certificate", label: "Income Certificate" },
  { value: "caste_certificate", label: "Caste Certificate" },
  { value: "caste_validity_certificate", label: "Caste Validity Certificate" },
  { value: "domicile_certificate", label: "Domicile Certificate" },
  { value: "nationality_certificate", label: "Nationality Certificate" },
];

const vaultDocumentCategories = [
  "Income Certificate",
  "Caste Certificate",
  "Caste Validity Certificate",
  "Domicile Certificate",
  "Nationality Certificate",
  "Aadhaar / Identity Proof",
  "Academic Marksheets",
  "Admission / Bonafide Certificate",
  "Bank Passbook",
  "Passport-size Photograph",
  "Disability Certificate",
  "Other Supporting Documents",
];

const editableFields = [
  { name: "applicant_name", label: "Applicant name" },
  { name: "certificate_number", label: "Certificate number" },
  { name: "issue_date", label: "Issue date" },
  { name: "issuing_authority", label: "Issuing authority" },
];

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export default function CertificateScanner({ onOpenLogin }) {
  const [activeTab, setActiveTab] = useState("vault"); // "vault" | "scanner"
  const [authed, setAuthed] = useState(isAuthenticated);
  const studentId = getStudentId();

  // Scanner states
  const [certificateType, setCertificateType] = useState("income_certificate");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [reviewComplete, setReviewComplete] = useState(false);
  const [isSavingToVault, setIsSavingToVault] = useState(false);
  const [vaultSaveMessage, setVaultSaveMessage] = useState("");

  // Vault states
  const [vaultDocuments, setVaultDocuments] = useState([]);
  const [isLoadingVault, setIsLoadingVault] = useState(false);
  const [vaultError, setVaultError] = useState("");
  const [uploadCategory, setUploadCategory] = useState("Income Certificate");
  const [vaultUploadFile, setVaultUploadFile] = useState(null);
  const [isUploadingToVault, setIsUploadingToVault] = useState(false);
  const [vaultActionMessage, setVaultActionMessage] = useState("");

  const loadVault = () => {
    const currentId = getStudentId();
    if (!currentId || !getAuthToken()) {
      setVaultDocuments([]);
      return;
    }
    setIsLoadingVault(true);
    setVaultError("");
    getStudentDocuments(currentId)
      .then((data) => {
        setVaultDocuments(data.documents || []);
      })
      .catch((err) => {
        setVaultError(err.message || "Could not load vault documents.");
      })
      .finally(() => {
        setIsLoadingVault(false);
      });
  };

  useEffect(() => {
    const handleAuthChange = () => {
      setAuthed(isAuthenticated());
      loadVault();
    };
    window.addEventListener("schobot-auth-changed", handleAuthChange);
    return () => {
      window.removeEventListener("schobot-auth-changed", handleAuthChange);
    };
  }, []);

  useEffect(() => {
    if (activeTab === "vault") {
      loadVault();
    }
  }, [activeTab, authed]);

  const handleScan = async (event) => {
    event.preventDefault();
    if (!file) return;

    setError("");
    setResult(null);
    setReviewComplete(false);
    setVaultSaveMessage("");
    setIsScanning(true);
    try {
      const scanResult = await scanCertificateDocument(certificateType, file, studentId, false);
      setResult(scanResult);
    } catch (scanError) {
      setError(scanError.message || "The document could not be scanned.");
    } finally {
      setIsScanning(false);
    }
  };

  const handleSaveScannedToVault = async () => {
    const currentId = getStudentId();
    if (!file || !currentId || !getAuthToken()) {
      setVaultSaveMessage("Please log in to your student account first to save documents to your vault.");
      onOpenLogin?.();
      return;
    }
    setIsSavingToVault(true);
    setVaultSaveMessage("");
    try {
      const selectedTypeLabel =
        certificateTypes.find((t) => t.value === certificateType)?.label || "Other Supporting Documents";
      await uploadStudentDocument(currentId, selectedTypeLabel, file, false);
      setVaultSaveMessage("✓ Document saved to My Document Vault! It will now automatically match relevant scholarships.");
    } catch (err) {
      setVaultSaveMessage(`Failed to save: ${err.message}`);
    } finally {
      setIsSavingToVault(false);
    }
  };

  const handleDirectVaultUpload = async (e) => {
    e.preventDefault();
    const currentId = getStudentId();
    if (!vaultUploadFile || !currentId || !getAuthToken()) {
      setVaultActionMessage("Please log in to your student account to upload documents.");
      onOpenLogin?.();
      return;
    }
    setIsUploadingToVault(true);
    setVaultActionMessage("");
    try {
      await uploadStudentDocument(currentId, uploadCategory, vaultUploadFile, true);
      setVaultActionMessage(`✓ "${vaultUploadFile.name}" successfully uploaded to your Document Vault!`);
      setVaultUploadFile(null);
      // Reset input element
      const fileInput = document.getElementById("vault-direct-file-input");
      if (fileInput) fileInput.value = "";
      loadVault();
    } catch (err) {
      setVaultActionMessage(`Upload failed: ${err.message}`);
    } finally {
      setIsUploadingToVault(false);
    }
  };

  const handleDeleteVaultDocument = async (docId, filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}" from your vault?`)) {
      return;
    }
    try {
      await deleteStudentDocument(docId, studentId);
      setVaultActionMessage(`✓ "${filename}" was removed from your vault.`);
      loadVault();
    } catch (err) {
      setVaultActionMessage(`Delete failed: ${err.message}`);
    }
  };

  const updateField = (fieldName, value) => {
    setReviewComplete(false);
    setResult((current) => ({
      ...current,
      fields: {
        ...current.fields,
        [fieldName]: {
          ...current.fields[fieldName],
          value,
          status: "manually_reviewed",
        },
      },
      missing_information: current.missing_information.filter((field) => field !== fieldName),
      uncertain_fields: current.uncertain_fields.filter((field) => field !== fieldName),
    }));
  };

  return (
    <main className="content-page certificate-scanner">
      <div className="page-heading">
        <p className="eyebrow">STUDENT DOCUMENT MANAGEMENT</p>
        <h1>Document Vault & OCR Scanner</h1>
        <p className="page-subtitle">
          Securely store and reuse your certificates across all scholarships, or extract information using OCR.
        </p>
      </div>

      {/* Tabs navigation */}
      <div className="document-vault-tabs">
        <button
          className={`vault-tab-btn ${activeTab === "vault" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("vault")}
          type="button"
        >
          📁 My Document Vault {vaultDocuments.length > 0 ? `(${vaultDocuments.length})` : ""}
        </button>
        <button
          className={`vault-tab-btn ${activeTab === "scanner" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("scanner")}
          type="button"
        >
          🔍 Certificate Scanner (OCR)
        </button>
      </div>

      {/* -------------------- TAB 1: DOCUMENT VAULT -------------------- */}
      {activeTab === "vault" && (
        <section className="vault-section">
          {!studentId || !getAuthToken() ? (
            <div className="vault-empty-notice vault-auth-card">
              <h3>Sign In to View Document Vault</h3>
              <p>Your Document Vault securely holds your verified certificates and automatically matches requirements across scholarship schemes.</p>
              <button
                type="button"
                className="scanner-submit vault-login-trigger-btn"
                onClick={() => onOpenLogin?.()}
              >
                Sign In to Vault
              </button>
            </div>
          ) : (
            <>
              {/* Direct Upload Card */}
              <form className="scanner-card vault-upload-card" onSubmit={handleDirectVaultUpload}>
                <div className="vault-upload-header">
                  <h3>Add Document to Vault</h3>
                  <small>Documents stored here are automatically reused across all scholarship applications.</small>
                </div>

                <div className="vault-form-row">
                  <label className="scanner-field">
                    <span>Document Category</span>
                    <select
                      disabled={isUploadingToVault}
                      onChange={(e) => setUploadCategory(e.target.value)}
                      value={uploadCategory}
                    >
                      {vaultDocumentCategories.map((cat) => (
                        <option key={cat} value={cat}>{cat}</option>
                      ))}
                    </select>
                  </label>

                  <label className="scanner-field">
                    <span>Select File (PDF, JPG, PNG - max 10 MB)</span>
                    <input
                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                      disabled={isUploadingToVault}
                      id="vault-direct-file-input"
                      onChange={(e) => setVaultUploadFile(e.target.files?.[0] || null)}
                      required
                      type="file"
                    />
                  </label>
                </div>

                <button
                  className="scanner-submit"
                  disabled={!vaultUploadFile || isUploadingToVault}
                  type="submit"
                >
                  {isUploadingToVault ? "Uploading to Vault…" : "Upload to Vault"}
                </button>

                {vaultActionMessage && (
                  <p className={vaultActionMessage.startsWith("✓") ? "vault-success-msg" : "scanner-error"}>
                    {vaultActionMessage}
                  </p>
                )}
              </form>

              {/* Vault Table / List */}
              <div className="vault-list-container">
                <div className="vault-list-header">
                  <h3>Stored Documents</h3>
                  <span className="vault-count-badge">{vaultDocuments.length} document{vaultDocuments.length !== 1 ? "s" : ""}</span>
                </div>

                {isLoadingVault ? (
                  <p role="status">Loading documents in vault...</p>
                ) : vaultError ? (
                  <p className="scanner-error" role="alert">{vaultError}</p>
                ) : vaultDocuments.length === 0 ? (
                  <div className="vault-empty-state">
                    <p>No documents uploaded yet. Upload your certificates above or scan a document to get started.</p>
                  </div>
                ) : (
                  <div className="vault-cards-grid">
                    {vaultDocuments.map((doc) => (
                      <article className="vault-doc-card" key={doc.id}>
                        <div className="vault-doc-type-line">
                          <span className="vault-type-pill">{doc.document_type}</span>
                          <span className={`doc-badge badge-${doc.verification_status}`}>
                            {doc.verification_status.replace("_", " ")}
                          </span>
                        </div>
                        <strong className="vault-doc-name">{doc.original_filename}</strong>
                        <div className="vault-doc-meta">
                          <span>Size: {formatBytes(doc.file_size)}</span>
                          <span>Uploaded: {new Date(doc.created_at).toLocaleDateString()}</span>
                          <span>OCR: {doc.ocr_status}</span>
                        </div>
                        {doc.rejection_reason && (
                          <small className="rejection-notice">Reason: {doc.rejection_reason}</small>
                        )}
                        <div className="vault-doc-actions">
                          {doc.download_url && (
                            <a
                              className="details-link"
                              href={doc.download_url}
                              rel="noopener noreferrer"
                              target="_blank"
                            >
                              View / Download ↗
                            </a>
                          )}
                          <button
                            className="vault-delete-btn"
                            onClick={() => handleDeleteVaultDocument(doc.id, doc.original_filename)}
                            type="button"
                          >
                            Delete
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {/* -------------------- TAB 2: CERTIFICATE SCANNER -------------------- */}
      {activeTab === "scanner" && (
        <section className="scanner-section">
          <form className="scanner-card" onSubmit={handleScan}>
            <label className="scanner-field">
              <span>Certificate type</span>
              <select
                disabled={isScanning}
                onChange={(event) => {
                  setCertificateType(event.target.value);
                  setResult(null);
                  setReviewComplete(false);
                  setVaultSaveMessage("");
                }}
                value={certificateType}
              >
                {certificateTypes.map((type) => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </label>
            {certificateType === "nationality_certificate" && (
              <p className="scanner-privacy">
                Maharashtra's verified service is combined with Age and Domicile; separate nationality-certificate
                requirements have not been established.
              </p>
            )}

            <label className="scanner-field">
              <span>Choose a PDF, JPG or PNG (maximum 10 MB)</span>
              <input
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                disabled={isScanning}
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setResult(null);
                  setReviewComplete(false);
                  setError("");
                  setVaultSaveMessage("");
                }}
                required
                type="file"
              />
            </label>

            <p className="scanner-privacy">
              OCR text detection assists in verifying certificate details. You can review detected values below and
              save the verified certificate directly to your Document Vault.
            </p>
            <button className="scanner-submit" disabled={!file || isScanning} type="submit">
              {isScanning ? "Uploading and scanning…" : "Scan document"}
            </button>
            {isScanning && (
              <>
                <progress aria-label="Upload and scan in progress" className="scanner-progress" />
                <p aria-live="polite" className="scanner-status" role="status">
                  Uploading the selected document and extracting readable text. This may take a moment.
                </p>
              </>
            )}
            {error && <p className="scanner-error" role="alert">{error}</p>}
          </form>

          {result && (
            <section aria-label="Scan results" className="scanner-results">
              <div className="scanner-result-heading">
                <div>
                  <p className="eyebrow">SCAN RESULT</p>
                  <h2>Manual review required</h2>
                </div>
                <div className="scanner-badge-group">
                  <span className="scanner-review-badge">
                    {reviewComplete ? "Review marked complete" : "Not verified"}
                  </span>
                </div>
              </div>

              <p className="scanner-caution">
                OCR can misread text. Confirm each value against the original document; this tool does not verify
                authenticity, a QR code, a digital signature, or legal validity.
              </p>

              <div className="scanner-fields">
                {editableFields.map(({ name, label }) => (
                  <label className="scanner-field" key={name}>
                    <span>{label}{result.fields[name]?.status === "not_detected" ? " — not detected" : ""}</span>
                    <input
                      onChange={(event) => updateField(name, event.target.value)}
                      placeholder="Review or enter a value"
                      value={result.fields[name]?.value || ""}
                    />
                    {result.fields[name]?.evidence && (
                      <small>Detected evidence: {result.fields[name].evidence}</small>
                    )}
                  </label>
                ))}
              </div>

              {result.possible_inconsistencies.length > 0 && (
                <div className="scanner-notice" role="status">
                  <h3>Possible inconsistencies</h3>
                  <ul>
                    {result.possible_inconsistencies.map((issue) => (
                      <li key={issue.field}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.extraction.warnings.length > 0 && (
                <div className="scanner-notice">
                  <h3>Unreadable or incomplete text</h3>
                  <ul>
                    {result.extraction.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                  </ul>
                </div>
              )}

              <section className="scanner-sources">
                <h3>Official references</h3>
                <p>{result.requirement_check.message}</p>
                {result.source_references.length > 0 ? (
                  <ul>
                    {result.source_references.map((source) => (
                      <li key={source.id}>
                        <a href={source.url} rel="noreferrer" target="_blank">{source.title}</a>
                        <span>{source.issuer} · {source.document_type}{source.version ? ` · ${source.version}` : ""}</span>
                        <p>{source.summary}</p>
                        <small>Limit: {source.limitations}</small>
                        {source.retrieved_passages?.map((passage, index) => (
                          <blockquote key={`${source.id}-${passage.page ?? "web"}-${index}`}>
                            <p>{passage.text}</p>
                            <small>
                              Retrieved source passage
                              {passage.page ? ` · PDF page ${passage.page}` : ""}
                              {` · similarity ${passage.score}`}
                            </small>
                          </blockquote>
                        ))}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No verified official reference is currently approved for this type.</p>
                )}
              </section>

              {/* Action buttons: Mark Complete and Save to Vault */}
              <div className="scanner-actions-bar">
                <button
                  className="scanner-submit"
                  onClick={() => setReviewComplete(true)}
                  type="button"
                >
                  Mark manual review complete
                </button>

                <button
                  className="scanner-submit vault-save-btn"
                  disabled={isSavingToVault}
                  onClick={handleSaveScannedToVault}
                  type="button"
                >
                  {isSavingToVault ? "Saving to Vault…" : "Save to My Document Vault 📁"}
                </button>
              </div>

              {vaultSaveMessage && (
                <p className={vaultSaveMessage.startsWith("✓") ? "vault-success-msg" : "scanner-error"}>
                  {vaultSaveMessage}
                </p>
              )}
            </section>
          )}
        </section>
      )}
    </main>
  );
}
