import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import MatchScore from "../components/MatchScore";
import ScholarshipDetailModal from "../components/ScholarshipDetailModal";
import { getRecommendations } from "../apiClient";
import { getStudentId, isStudentProfileComplete, loadStudentProfile } from "../data/profile";
import { dedupeByScholarshipId } from "../data/scholarships";

function recommendationStatus(status) {
  if (status === "likely_eligible") return "Likely eligible";
  if (status === "needs_verification") return "Needs verification";
  return status.replaceAll("_", " ");
}

function isEligibleRecommendation(item) {
  return item.match_status === "likely_eligible" || item.match_status === "needs_verification";
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

function formatDeadline(value) {
  if (!value) return "TBD";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export default function EligibleScholarships() {
  const [profile, setProfile] = useState(loadStudentProfile);
  const [recommendations, setRecommendations] = useState([]);
  const [studentId, setStudentId] = useState(getStudentId);
  const [isLoading, setIsLoading] = useState(() => (
    Boolean(getStudentId()) && isStudentProfileComplete(loadStudentProfile())
  ));
  const [loadError, setLoadError] = useState("");
  const [rawRecommendations, setRawRecommendations] = useState([]);
  const [hasLoadedRecommendations, setHasLoadedRecommendations] = useState(false);
  const [debugResponse, setDebugResponse] = useState(null);
  const [debugError, setDebugError] = useState("");
  const [isDebugLoading, setIsDebugLoading] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [selectedScholarship, setSelectedScholarship] = useState(null);
  const profileComplete = isStudentProfileComplete(profile);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Eligible Scholarships | Schobot";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    const updateProfile = () => {
      const nextProfile = loadStudentProfile();
      const nextStudentId = getStudentId();
      setProfile(nextProfile);
      setStudentId(nextStudentId);
      setIsLoading(Boolean(nextStudentId) && isStudentProfileComplete(nextProfile));
      setLoadError("");
      setRawRecommendations([]);
      setHasLoadedRecommendations(false);
      setDebugResponse(null);
      setDebugError("");
      setSelectedScholarship(null);
    };
    window.addEventListener("schobot-profile-updated", updateProfile);
    window.addEventListener("storage", updateProfile);
    return () => {
      window.removeEventListener("schobot-profile-updated", updateProfile);
      window.removeEventListener("storage", updateProfile);
    };
  }, []);

  useEffect(() => {
    if (!studentId || !profileComplete) {
      return undefined;
    }

    let cancelled = false;
    getRecommendations(studentId)
      .then((response) => {
        if (cancelled) return;
        if (!Array.isArray(response.recommendations)) {
          throw new Error("The server returned an invalid recommendations response.");
        }
        const eligibleRecommendations = dedupeByScholarshipId(
          response.recommendations.filter(isEligibleRecommendation),
        );
        if (import.meta.env.DEV) {
          console.debug("Schobot recommendations response:", {
            total: response.recommendations.length,
            statusCounts: response.recommendations.reduce((counts, item) => {
              const status = item.match_status || "missing";
              counts[status] = (counts[status] || 0) + 1;
              return counts;
            }, {}),
            firstItems: response.recommendations.slice(0, 5).map((item) => ({
              scholarship_id: item.scholarship_id,
              scholarship_name: item.scholarship_name,
              match_status: item.match_status,
            })),
            eligibleCount: eligibleRecommendations.length,
          });
        }
        setRawRecommendations(response.recommendations);
        setHasLoadedRecommendations(true);
        setRecommendations(eligibleRecommendations);
      })
      .catch((error) => {
        if (cancelled) return;
        console.warn("Could not load scholarship recommendations.", error);
        setLoadError("Unable to load recommendations right now. Please ensure the backend is running and try again.");
        setRecommendations([]);
        setHasLoadedRecommendations(false);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [studentId, profileComplete]);

  const handleDebug = async () => {
    setIsDebugLoading(true);
    setDebugError("");
    try {
      const response = await getRecommendations(studentId);
      setDebugResponse(response);
      setIsDebugOpen(true);
      console.debug("Raw Schobot recommendations response:", response);
    } catch (error) {
      console.error("Could not fetch raw Schobot recommendations.", error);
      setDebugResponse(null);
      setDebugError(error.message || "Unable to fetch the raw recommendations response.");
    } finally {
      setIsDebugLoading(false);
    }
  };

  const showCompleteProfile = !profileComplete || !studentId;
  const emptyMessage = "No scholarships match your current profile (education level, category, domicile, income). Try adjusting your profile or contact support.";
  const displayedScholarships = recommendations;
  const count = displayedScholarships.length;

  return (
    <>
    <main className="content-page">
      <div className="page-heading">
        <p className="eyebrow">MATCHED TO YOUR PROFILE</p>
        <h1>Eligible Scholarships</h1>
        <p className="page-subtitle">
          {showCompleteProfile
            ? "Complete your profile to see eligible scholarships."
            : recommendations.length === 0 && !isLoading && !loadError
              ? emptyMessage
              : "Scholarships evaluated for your profile by Schobot."}
        </p>
      </div>

      {import.meta.env.DEV && studentId && (
        <section className="recommendation-debug">
          <button className="details-link recommendation-debug-button" disabled={isDebugLoading} onClick={handleDebug} type="button">
            {isDebugLoading ? "Loading debug response..." : "Debug recommendations"}
          </button>
          {debugError && <p role="alert">{debugError}</p>}
          {debugResponse && (
            <details open={isDebugOpen} onToggle={(event) => setIsDebugOpen(event.currentTarget.open)}>
              <summary>Raw recommendations JSON</summary>
              <pre>{JSON.stringify(debugResponse, null, 2)}</pre>
            </details>
          )}
        </section>
      )}

      {isLoading ? (
        <div className="empty-state" role="status">Loading your recommendations...</div>
      ) : loadError ? (
        <div className="empty-state" role="alert">
          <Icon name="filter" size={24} />
          <strong>{loadError}</strong>
        </div>
      ) : showCompleteProfile ? (
        <div className="empty-state">
          <Icon name="user" size={24} />
          <strong>Complete your profile to see eligible scholarships.</strong>
          <span>
            {profileComplete
              ? "Save your profile while the backend is available to generate recommendations."
              : "Add your education, course, state, category, and family income to get started."}
          </span>
          <Link className="primary-button" to="/profile">Go to My Profile</Link>
        </div>
      ) : recommendations.length === 0 ? (
        <div className="empty-state">
          <Icon name="filter" size={24} />
          <strong>{emptyMessage}</strong>
          <span>Review your saved profile details, then save it again to refresh recommendations.</span>
          {hasLoadedRecommendations && rawRecommendations.length > 0 && (
            <small>
              {import.meta.env.DEV
                ? `Backend returned ${rawRecommendations.length} recommendations; none were marked likely eligible or needing verification.`
                : "No scholarships were marked likely eligible or needing verification."}
            </small>
          )}
        </div>
      ) : (
        <>
          <div className="eligible-summary">
            <span className="eligible-summary-icon"><Icon name="check" size={19} /></span>
            <span>
              <strong>{count} eligible scholarships</strong>
              <small>eligible scholarships returned by Schobot</small>
            </span>
          </div>

          <div className="eligible-list">
            {displayedScholarships.map((recommendation) => (
              <article
                aria-label={`Open details and document checklist for ${recommendation.scholarship_name || "scholarship"}`}
                aria-haspopup="dialog"
                className="eligible-card eligible-card-clickable"
                key={recommendation.scholarship_id}
                onClick={() => setSelectedScholarship(recommendation)}
                onKeyDown={(event) => {
                  if (event.target === event.currentTarget && ["Enter", " "].includes(event.key)) {
                    event.preventDefault();
                    setSelectedScholarship(recommendation);
                  }
                }}
                onKeyUp={(event) => {
                  if (event.target === event.currentTarget && event.key === " ") {
                    event.preventDefault();
                    setSelectedScholarship(recommendation);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <span className="scholarship-symbol"><Icon name="scholarship" size={20} /></span>
                <div className="eligible-card-main">
                  <div className="scholarship-title-line">
                    <h2>{recommendation.scholarship_name || "Scholarship"}</h2>
                    <span className={`type-badge ${(recommendation.scholarship_type || "government").toLowerCase()}`}>
                      {recommendation.scholarship_type || "Type not specified"}
                    </span>
                  </div>
                  <div className="scholarship-meta">
                    <span>{recommendation.state || "State not specified"}</span><i />
                    <span className={`recommendation-status status-${recommendation.match_status}`}>
                      {recommendationStatus(recommendation.match_status)}
                    </span>
                    <i />
                    <span>Deadline: {formatDeadline(recommendation.deadline)}</span>
                  </div>
                  <p>
                    {recommendation.passed_rules?.length || 0} requirements passed
                    {recommendation.unknown_rules?.length
                      ? ` · ${recommendation.unknown_rules.length} need verification`
                      : ""}
                  </p>
                  <div className="recommendation-actions">
                    {officialWebsiteUrl(recommendation.official_link) ? (
                      <a
                        className="recommendation-website-link"
                        href={officialWebsiteUrl(recommendation.official_link)}
                        rel="noopener noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        target="_blank"
                      >
                        Apply now
                      </a>
                    ) : (
                      <span className="recommendation-website-missing">No official website available</span>
                    )}
                    <span className="open-document-checklist">Open details and document checklist</span>
                  </div>
                </div>
                <MatchScore score={Math.round(recommendation.match_score || 0)} />
              </article>
            ))}
          </div>
        </>
      )}
    </main>
    {selectedScholarship && studentId && (
      <ScholarshipDetailModal
        onClose={() => setSelectedScholarship(null)}
        recommendation={selectedScholarship}
        studentId={studentId}
      />
    )}
    </>
  );
}
