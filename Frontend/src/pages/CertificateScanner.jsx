import { useState } from "react";
import { scanCertificateDocument } from "../apiClient";
import "./CertificateScanner.css";

const certificateTypes = [
  { value: "income_certificate", label: "Income Certificate" },
  { value: "caste_certificate", label: "Caste Certificate" },
  { value: "caste_validity_certificate", label: "Caste Validity Certificate" },
  { value: "domicile_certificate", label: "Domicile Certificate" },
  { value: "nationality_certificate", label: "Nationality Certificate" },
];

const editableFields = [
  { name: "applicant_name", label: "Applicant name" },
  { name: "certificate_number", label: "Certificate number" },
  { name: "issue_date", label: "Issue date" },
  { name: "issuing_authority", label: "Issuing authority" },
];

export default function CertificateScanner() {
  const [certificateType, setCertificateType] = useState("income_certificate");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [reviewComplete, setReviewComplete] = useState(false);

  const handleScan = async (event) => {
    event.preventDefault();
    if (!file) return;

    setError("");
    setResult(null);
    setReviewComplete(false);
    setIsScanning(true);
    try {
      const scanResult = await scanCertificateDocument(certificateType, file);
      setResult(scanResult);
    } catch (scanError) {
      setError(scanError.message || "The document could not be scanned.");
    } finally {
      setIsScanning(false);
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
        <p className="eyebrow">DOCUMENT TOOLS</p>
        <h1>Certificate Scanner</h1>
        <p className="page-subtitle">
          Review text detected in supported Maharashtra certificate documents.
          Scanning does not establish authenticity or legal validity.
        </p>
      </div>

      <form className="scanner-card" onSubmit={handleScan}>
        <label className="scanner-field">
          <span>Certificate type</span>
          <select
            disabled={isScanning}
            onChange={(event) => {
              setCertificateType(event.target.value);
              setResult(null);
              setReviewComplete(false);
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
            }}
            required
            type="file"
          />
        </label>

        <p className="scanner-privacy">
          Files and extracted text are processed for this request only and are not saved by this feature.
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
            <span className="scanner-review-badge">
              {reviewComplete ? "Review marked complete" : "Not verified"}
            </span>
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

          <button
            className="scanner-submit"
            onClick={() => setReviewComplete(true)}
            type="button"
          >
            Mark manual review complete
          </button>
          <p className="scanner-privacy">
            Corrections and review status remain in this page only and are cleared when you leave or refresh it.
          </p>
        </section>
      )}
    </main>
  );
}
