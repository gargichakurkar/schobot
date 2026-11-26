import { useEffect, useRef, useState } from "react";
import ProfileForm from "../components/ProfileForm";
import {
  getProfile,
  getRecommendations,
  submitProfileAndGetRecommendations,
  updateProfile,
} from "../apiClient";
import {
  clearStudentId,
  getStudentId,
  isAuthenticated,
  loadStudentProfile,
  logoutStudent,
  profileFromBackend,
  saveStudentId,
  saveStudentProfile,
} from "../data/profile";

export default function MyProfile({ onOpenLogin }) {
  const [profile, setProfile] = useState(loadStudentProfile);
  const [saveMessage, setSaveMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saveErrorDetail, setSaveErrorDetail] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [authed, setAuthed] = useState(isAuthenticated);
  const profileEdited = useRef(false);

  useEffect(() => {
    const handleAuthChange = () => {
      setAuthed(isAuthenticated());
      const studentId = getStudentId();
      if (studentId) {
        getProfile(studentId)
          .then((serverProfile) => {
            const updatedProfile = profileFromBackend(serverProfile, loadStudentProfile());
            setProfile(updatedProfile);
            saveStudentProfile(updatedProfile);
          })
          .catch(() => {
            setProfile(loadStudentProfile());
          });
      } else {
        setProfile(loadStudentProfile());
      }
    };

    window.addEventListener("schobot-auth-changed", handleAuthChange);
    return () => {
      window.removeEventListener("schobot-auth-changed", handleAuthChange);
    };
  }, []);

  useEffect(() => {
    const studentId = getStudentId();
    if (!studentId) return undefined;

    let cancelled = false;
    getProfile(studentId)
      .then((serverProfile) => {
        if (cancelled || profileEdited.current) return;
        const updatedProfile = profileFromBackend(serverProfile, loadStudentProfile());
        setProfile(updatedProfile);
        saveStudentProfile(updatedProfile);
      })
      .catch((error) => {
        if (cancelled) return;
        console.warn("Could not load the Schobot profile from the server.", error);
        setSaveError("Unable to load your profile from the server. Your saved profile on this device is still available.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleChange = (event) => {
    profileEdited.current = true;
    setProfile((current) => ({ ...current, [event.target.name]: event.target.value }));
    setSaveMessage("");
    setSaveError("");
    setSaveErrorDetail("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaveMessage("");
    setSaveError("");
    setSaveErrorDetail("");
    setIsSaving(true);

    try {
      saveStudentProfile(profile);
      window.dispatchEvent(new Event("schobot-profile-updated"));
    } catch (error) {
      console.error("Could not save the Schobot profile locally.", error);
      setSaveError("Could not save your profile on this device. Check your browser storage and try again.");
      setIsSaving(false);
      return;
    }

    const existingStudentId = getStudentId();
    let student;
    let recommendationWarning = "";
    try {
      if (existingStudentId) {
        student = await updateProfile(existingStudentId, profile);
        if (student?.id !== existingStudentId) {
          throw new Error("Server response did not confirm the existing student ID.");
        }

        try {
          const response = await getRecommendations(existingStudentId);
          if (!Array.isArray(response?.recommendations)) {
            throw new Error("The server returned an invalid recommendations response.");
          }
        } catch (error) {
          console.warn("Profile updated, but recommendations could not be loaded.", error);
          recommendationWarning = "Recommendations could not be loaded. You can retry from Eligible Scholarships.";
        }
      } else {
        const response = await submitProfileAndGetRecommendations(profile);
        student = response?.student;
        if (!student?.id) {
          throw new Error("Server response did not include a student ID.");
        }
      }
    } catch (error) {
      console.error("Could not save the Schobot profile to the server.", error);
      if (!existingStudentId) {
        try {
          clearStudentId();
        } catch (storageError) {
          console.warn("Could not clear the old Schobot student ID.", storageError);
        }
      }
      window.dispatchEvent(new Event("schobot-profile-updated"));
      setSaveError("Could not save your profile to the server right now. Your data is saved locally.");
      setSaveErrorDetail(error.message);
      setIsSaving(false);
      return;
    }

    try {
      saveStudentId(student.id);
      const savedProfile = profileFromBackend(student, profile);
      saveStudentProfile(savedProfile);
      setProfile(savedProfile);
      window.dispatchEvent(new Event("schobot-profile-updated"));
      setSaveMessage(
        existingStudentId
          ? "Your profile has been updated."
          : "Your profile has been saved and recommendations are ready.",
      );
      setSaveErrorDetail(recommendationWarning);
    } catch (error) {
      console.error("The server saved the profile, but the browser could not finish local synchronization.", error);
      setSaveError("Your profile was saved to the server, but this browser could not store its student ID.");
      setSaveErrorDetail(error.message);
    }
    setIsSaving(false);
  };

  const activeStudentId = getStudentId();

  return (
    <main className="content-page">
      <div className="page-heading">
        <p className="eyebrow">YOUR DETAILS</p>
        <h1>Student Profile</h1>
        <p className="page-subtitle">Tell us about yourself so we can find the best scholarships for you.</p>
      </div>

      <div className={`profile-auth-status ${authed ? "profile-auth-logged-in" : "profile-auth-logged-out"}`}>
        {authed ? (
          <div className="profile-auth-content">
            <span className="profile-auth-badge">Active Session</span>
            <span>
              Signed in as <strong>{profile.full_name || "Student"}</strong>
              {profile.email ? ` (${profile.email})` : activeStudentId ? ` (ID: ${activeStudentId.slice(0, 8)}…)` : ""}
            </span>
            <button
              type="button"
              className="profile-auth-action-btn"
              onClick={() => logoutStudent()}
            >
              Sign Out
            </button>
          </div>
        ) : (
          <div className="profile-auth-content">
            <span>Already have a Schobot profile or Document Vault?</span>
            <button
              type="button"
              className="profile-auth-action-btn"
              onClick={() => onOpenLogin?.()}
            >
              Sign In to Your Account
            </button>
          </div>
        )}
      </div>

      <ProfileForm
        onChange={handleChange}
        onSubmit={handleSubmit}
        profile={profile}
        saveError={saveError}
        saveErrorDetail={saveErrorDetail}
        saveMessage={saveMessage}
        isSaving={isSaving}
      />
    </main>
  );
}
