import { useEffect, useState } from "react";
import { getReminderPreferences, updateReminderPreferences } from "../apiClient";
import { translate } from "../i18n";

const channels = ["email", "sms", "whatsapp"];

export default function ReminderPreferences({ studentId, scholarshipId, language = "en" }) {
  const [enabled, setEnabled] = useState(false);
  const [channel, setChannel] = useState("email");
  const [loading, setLoading] = useState(Boolean(studentId));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!studentId) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    getReminderPreferences(studentId, scholarshipId)
      .then(({ preferences }) => {
        if (cancelled) return;
        const preference = preferences?.find((item) => item.scholarship_id === scholarshipId);
        if (preference) {
          setEnabled(preference.enabled);
          setChannel(preference.channel);
        }
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError.message || "Could not load reminder preferences.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, scholarshipId]);

  const save = async (nextEnabled, nextChannel) => {
    if (!studentId) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await updateReminderPreferences({
        studentId,
        scholarshipId,
        channel: nextChannel,
        enabled: nextEnabled,
      });
      setEnabled(nextEnabled);
      setChannel(nextChannel);
      setMessage("Preference saved. Reminder delivery is not configured yet.");
    } catch (saveError) {
      setError(saveError.message || "Could not save reminder preference.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="reminder-preferences">
      <h3>{translate(language, "reminderTitle")}</h3>
      {!studentId ? <p>Save your student profile to configure reminders.</p> : null}
      <label className="reminder-toggle">
        <input
          checked={enabled}
          disabled={!studentId || loading || saving}
          onChange={(event) => save(event.target.checked, channel)}
          type="checkbox"
        />
        <span>{translate(language, "reminderEnable")}</span>
      </label>
      <label className="reminder-channel">
        <span>{translate(language, "reminderChannel")}</span>
        <select
          disabled={!studentId || loading || saving}
          onChange={(event) => save(enabled, event.target.value)}
          value={channel}
        >
          {channels.map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</option>)}
        </select>
      </label>
      {loading || saving ? <small role="status">{loading ? "Loading…" : "Saving…"}</small> : null}
      {error ? <p className="modal-error" role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
    </section>
  );
}
