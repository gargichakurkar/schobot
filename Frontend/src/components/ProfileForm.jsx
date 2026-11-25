import { categoriesProfile, educationLevelsProfile } from "../data/profile";

const indianStates = [
  "Andhra Pradesh",
  "Assam",
  "Bihar",
  "Chhattisgarh",
  "Delhi",
  "Goa",
  "Gujarat",
  "Haryana",
  "Himachal Pradesh",
  "Jharkhand",
  "Karnataka",
  "Kerala",
  "Madhya Pradesh",
  "Maharashtra",
  "Manipur",
  "Meghalaya",
  "Mizoram",
  "Nagaland",
  "Odisha",
  "Punjab",
  "Rajasthan",
  "Sikkim",
  "Tamil Nadu",
  "Telangana",
  "Tripura",
  "Uttar Pradesh",
  "Uttarakhand",
  "West Bengal",
];

const genders = ["Female", "Male", "Other", "Prefer not to say"];
const years = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"];

function TextField({ label, name, profile, onChange, type = "text", options, ...attributes }) {
  return (
    <label className="profile-field">
      <span>{label}</span>
      {options ? (
        <select name={name} onChange={onChange} value={profile[name]} {...attributes}>
          <option value="">Select an option</option>
          {options.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      ) : (
        <input
          name={name}
          onChange={onChange}
          type={type}
          value={profile[name]}
          {...attributes}
        />
      )}
    </label>
  );
}

function BooleanSelectField({ label, name, profile, onChange, helper }) {
  const value =
    profile[name] === true || profile[name] === "true"
      ? "true"
      : profile[name] === false || profile[name] === "false"
      ? "false"
      : "";
  return (
    <label className="profile-field">
      <span>{label}</span>
      <select name={name} onChange={onChange} value={value}>
        <option value="">Not Specified / Unknown</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
      {helper && <small style={{ color: "#666", fontSize: "0.82rem", marginTop: "2px" }}>{helper}</small>}
    </label>
  );
}

function ProfileSection({ title, description, children }) {
  return (
    <section className="profile-section">
      <div className="profile-section-heading">
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      <div className="profile-fields">{children}</div>
    </section>
  );
}

export default function ProfileForm({
  profile,
  onChange,
  onSubmit,
  saveMessage,
  saveError,
  saveErrorDetail,
  isSaving,
}) {
  return (
    <form className="profile-form-card" onSubmit={onSubmit}>
      <ProfileSection title="Personal Information">
        <TextField autoComplete="name" label="Full Name" name="full_name" onChange={onChange} profile={profile} required />
        <TextField autoComplete="email" label="Email" name="email" onChange={onChange} profile={profile} required type="email" />
        <TextField autoComplete="tel" label="Phone Number" name="phone_number" onChange={onChange} profile={profile} required type="tel" />
        <TextField label="Date of Birth" name="date_of_birth" onChange={onChange} profile={profile} required type="date" />
      </ProfileSection>

      <ProfileSection title="Education Details">
        <label className="profile-field">
          <span>Education Level</span>
          <select name="education_level" onChange={onChange} value={profile.education_level} required>
            <option value="">Select education level</option>
            {educationLevelsProfile.map((level) => (
              <option key={level} value={level}>{level}</option>
            ))}
          </select>
        </label>
        <TextField label="Course" name="course" onChange={onChange} profile={profile} required />
        <TextField label="Study Year" name="study_year" onChange={onChange} options={years} profile={profile} required />
        <TextField label="College/University Name" name="college_name" onChange={onChange} profile={profile} required />
      </ProfileSection>

      <ProfileSection title="Additional Information">
        <TextField label="State" name="state" onChange={onChange} options={indianStates} profile={profile} required />
        <label className="profile-field">
          <span>Category (caste)</span>
          <select name="category" onChange={onChange} value={profile.category} required>
            <option value="">Select category</option>
            {categoriesProfile.map((category) => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>
        </label>
        <TextField
          label="Annual Family Income (₹)"
          min="0"
          name="annual_family_income"
          onChange={onChange}
          profile={profile}
          required
          step="1"
          type="number"
        />
        <TextField label="Gender" name="gender" onChange={onChange} options={genders} profile={profile} required />
      </ProfileSection>

      <ProfileSection title="Academic Performance">
        <TextField
          label={profile.score_type === "CGPA" ? "CGPA" : "Percentage / CGPA"}
          max={profile.score_type === "CGPA" ? "10" : "100"}
          min="0"
          name="academic_score"
          onChange={onChange}
          profile={profile}
          required
          step="any"
          type="number"
        />
        <TextField
          label="Score Type"
          name="score_type"
          onChange={onChange}
          options={["Percentage", "CGPA"]}
          profile={profile}
          required
        />
      </ProfileSection>

      <ProfileSection
        title="Special Eligibility & Quota Criteria (Optional)"
        description="Optional fields used to match specific quota schemes (Swanath, Railway wards, PWD, and maintenance allowances)."
      >
        <BooleanSelectField
          label="Person with Disability (PWD)?"
          name="has_disability_certificate"
          profile={profile}
          onChange={onChange}
          helper="Do you hold a disability certificate?"
        />
        {(profile.has_disability_certificate === true || profile.has_disability_certificate === "true" || profile.category === "PWD") && (
          <>
            <TextField
              label="Disability Percentage (%)"
              max="100"
              min="0"
              name="disability_percentage"
              onChange={onChange}
              profile={profile}
              type="number"
            />
            <BooleanSelectField
              label="Have Valid UDID Card?"
              name="has_udid"
              profile={profile}
              onChange={onChange}
            />
          </>
        )}
        <BooleanSelectField
          label="Are you an orphan?"
          name="is_orphan"
          profile={profile}
          onChange={onChange}
          helper="For AICTE Swanath and orphan grants."
        />
        <BooleanSelectField
          label="Lost parents due to Covid-19?"
          name="parent_death_due_to_covid"
          profile={profile}
          onChange={onChange}
        />
        <BooleanSelectField
          label="Ward of Armed Forces / CAPF Martyr?"
          name="parent_martyred_armed_forces"
          profile={profile}
          onChange={onChange}
        />
        <BooleanSelectField
          label="Dependent of Railway (RPF / RPSF) Personnel?"
          name="is_dependent_of_rpf_rpsf"
          profile={profile}
          onChange={onChange}
        />
        <BooleanSelectField
          label="Passed previous academic year?"
          name="previous_year_passed"
          profile={profile}
          onChange={onChange}
          helper="Passed previous year without backlog."
        />
        <BooleanSelectField
          label="Receiving any other scholarship?"
          name="receives_other_scholarship"
          profile={profile}
          onChange={onChange}
        />
      </ProfileSection>

      {(saveMessage || saveError) && (
        <div className={`save-feedback${saveError ? " save-feedback-error" : ""}`} role={saveError ? "alert" : "status"}>
          <p>{saveError || saveMessage}</p>
          {saveErrorDetail && <small>{saveErrorDetail}</small>}
        </div>
      )}
      <div className="profile-form-actions">
        <span className="local-save-note">Your profile is saved on this device.</span>
        <div className="profile-form-buttons">
          <button className="primary-button" disabled={isSaving} type="submit">
            {isSaving ? "Saving..." : "Save Profile"}
          </button>
        </div>
      </div>
    </form>
  );
}
