import { normalizeCategory, normalizeEducationLevel } from "./data/profile";

export const apiBaseUrl = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");

async function request(path, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  let response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        ...(options.body && !isFormData ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    window.clearTimeout(timeoutId);
    if (controller.signal.aborted) {
      throw new Error(`Backend request to ${path} timed out after 30 seconds at ${apiBaseUrl}.`, { cause: error });
    }
    throw new Error(
      `Could not reach the backend at ${apiBaseUrl}. Check that it is running and allows this frontend origin (CORS).`,
      { cause: error },
    );
  }

  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  const isJson = contentType.includes("application/json") || contentType.includes("+json");
  if (!response.ok) {
    let detail = "";
    try {
      if (isJson) {
        const body = await response.json();
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          detail = body.detail
            .map((item) => `${item.loc?.join(".") || "Request"}: ${item.msg || "Invalid value"}`)
            .join("; ");
        }
      } else {
        detail = (await response.text())
          .replace(/<[^>]*>/g, " ")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 300);
      }
    } catch (error) {
      if (!(error instanceof SyntaxError)) {
        console.warn("Could not read the Schobot server error response.", error);
      }
    }
    window.clearTimeout(timeoutId);
    throw new Error(`${detail || response.statusText || "The server returned an error"} for ${apiBaseUrl}${path} (HTTP ${response.status}).`);
  }

  if (!isJson) {
    window.clearTimeout(timeoutId);
    throw new Error(`Server returned an invalid response for ${apiBaseUrl}${path} (HTTP ${response.status}; expected JSON).`);
  }

  try {
    const data = await response.json();
    window.clearTimeout(timeoutId);
    return data;
  } catch (error) {
    window.clearTimeout(timeoutId);
    if (controller.signal.aborted) {
      throw new Error(`Backend request to ${path} timed out after 30 seconds at ${apiBaseUrl}.`, { cause: error });
    }
    throw new Error(`Server returned an invalid response for ${apiBaseUrl}${path} (HTTP ${response.status}; response was not valid JSON).`, { cause: error });
  }
}

function numericValue(value) {
  if (value == null || String(value).trim() === "") return null;
  const number = Number(String(value).replace(/[₹,\s]/g, ""));
  return Number.isFinite(number) ? number : null;
}

function booleanValue(val) {
  if (val === true || val === "true") return true;
  if (val === false || val === "false") return false;
  return null;
}

function profilePayload(profile) {
  return {
    full_name: profile.full_name,
    email: profile.email || null,
    education_level: normalizeEducationLevel(profile.education_level) || null,
    course: profile.course || null,
    study_year: profile.study_year || null,
    college_name: profile.college_name || null,
    academic_score: numericValue(profile.academic_score),
    score_type: profile.score_type || null,
    domicile_state: profile.state || null,
    study_state: profile.state || null,
    category: normalizeCategory(profile.category) || null,
    gender: profile.gender || null,
    disability_percentage: numericValue(profile.disability_percentage),
    has_valid_disability_certificate: booleanValue(profile.has_valid_disability_certificate),
    has_udid: booleanValue(profile.has_udid),
    has_disability_certificate: booleanValue(profile.has_disability_certificate),
    is_orphan: booleanValue(profile.is_orphan),
    parent_death_due_to_covid: booleanValue(profile.parent_death_due_to_covid),
    parent_martyred_armed_forces: booleanValue(profile.parent_martyred_armed_forces),
    is_dependent_of_rpf_rpsf: booleanValue(profile.is_dependent_of_rpf_rpsf),
    parent_service_category: profile.parent_service_category || null,
    previous_year_passed: booleanValue(profile.previous_year_passed),
    receives_other_scholarship: booleanValue(profile.receives_other_scholarship),
    annual_family_income: numericValue(profile.annual_family_income),
    has_income_certificate: booleanValue(profile.has_income_certificate),
    profile_completed: true,
  };
}

export function createProfile(profile) {
  return request("/api/profiles", {
    method: "POST",
    body: JSON.stringify(profilePayload(profile)),
  });
}

export function submitProfileAndGetRecommendations(profile) {
  return request("/api/profile/submit-and-recommend", {
    method: "POST",
    body: JSON.stringify(profilePayload(profile)),
  });
}

export function getProfile(studentId) {
  return request(`/api/profiles/${encodeURIComponent(studentId)}`);
}

export function getHealth() {
  return request("/api/health");
}

export function scanCertificateDocument(certificateType, file) {
  const formData = new FormData();
  formData.append("certificate_type", certificateType);
  formData.append("file", file);
  return request(
    "/api/documents/scan",
    {
      method: "POST",
      body: formData,
    },
    120000,
  );
}

export function updateProfile(studentId, profile) {
  return request(`/api/profiles/${encodeURIComponent(studentId)}`, {
    method: "PUT",
    body: JSON.stringify(profilePayload(profile)),
  });
}

export function getRecommendations(studentId) {
  return request(`/api/recommendations/${encodeURIComponent(studentId)}`);
}

export function updateScholarshipProgress(studentId, scholarshipId, progress) {
  return request(
    `/api/recommendations/${encodeURIComponent(studentId)}/scholarship/${encodeURIComponent(scholarshipId)}/progress`,
    {
      method: "PATCH",
      body: JSON.stringify(progress),
    },
  );
}

export function getScholarshipDocuments(studentId, scholarshipId) {
  return request(
    `/api/recommendations/${encodeURIComponent(studentId)}/scholarship/${encodeURIComponent(scholarshipId)}/documents`,
  );
}

export function updateScholarshipDocument(studentId, scholarshipId, documentName, document) {
  return request(
    `/api/recommendations/${encodeURIComponent(studentId)}/scholarship/${encodeURIComponent(scholarshipId)}/documents/${encodeURIComponent(documentName)}`,
    {
      method: "PATCH",
      body: JSON.stringify(document),
    },
  );
}

export function getScholarship(scholarshipId) {
  return request(`/api/scholarships/${encodeURIComponent(scholarshipId)}`);
}

export function getScholarshipEligibility(scholarshipId, studentId) {
  return request(
    `/api/scholarships/${encodeURIComponent(scholarshipId)}/eligibility/${encodeURIComponent(studentId)}`,
  );
}

export function getScholarships(filters = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) query.set(key, value);
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request(`/api/scholarships${suffix}`);
}

export function getReminderPreferences(studentId, scholarshipId) {
  const query = new URLSearchParams({ student_id: studentId });
  if (scholarshipId) query.set("scholarship_id", scholarshipId);
  return request(`/api/reminders/preferences?${query.toString()}`);
}

export function updateReminderPreferences({ studentId, scholarshipId, channel, enabled }) {
  return request("/api/reminders/preferences", {
    method: "POST",
    body: JSON.stringify({
      student_id: studentId,
      scholarship_id: scholarshipId,
      channel,
      enabled,
    }),
  });
}

export function sendChatMessage({ message, studentId, conversationHistory = [] }) {
  return request("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      student_id: studentId || null,
      conversation_history: conversationHistory,
    }),
  });
}
