import { useEffect, useRef, useState } from "react";
import ProfileForm from "../components/ProfileForm";
import { getProfile, submitProfileAndGetRecommendations } from "../apiClient";
import {
  getStudentId,
  clearStudentId,
  loadStudentProfile,
  profileFromBackend,
  saveStudentId,
  saveStudentProfile,
} from "../data/profile";

export default function MyProfile() {
  const [profile, setProfile] = useState(loadStudentProfile);
  const [saveMessage, setSaveMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saveErrorDetail, setSaveErrorDetail] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const profileEdited = useRef(false);

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

    let student;
    try {
      const response = await submitProfileAndGetRecommendations(profile);
      student = response?.student;
      if (!student?.id) {
        throw new Error("Server response did not include a student ID.");
      }
    } catch (error) {
      console.error("Could not save the Schobot profile to the server.", error);
      try {
        clearStudentId();
      } catch (storageError) {
        console.warn("Could not clear the old Schobot student ID.", storageError);
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
      setSaveMessage("Your profile has been saved and recommendations are ready.");
    } catch (error) {
      console.error("The server saved the profile, but the browser could not finish local synchronization.", error);
      setSaveError("Your profile was saved to the server, but this browser could not store its student ID.");
      setSaveErrorDetail(error.message);
    }
    setIsSaving(false);
  };

  return (
    <main className="content-page">
      <div className="page-heading">
        <p className="eyebrow">YOUR DETAILS</p>
        <h1>Student Profile</h1>
        <p className="page-subtitle">Tell us about yourself so we can find the best scholarships for you.</p>
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
