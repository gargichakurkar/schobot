import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginStudent, requestOTP, verifyOTPAndSetPassword } from "../apiClient";
import Icon from "./Icon";

export default function LoginModal({ isOpen, onClose, onSuccess }) {
  const [mode, setMode] = useState("login"); // "login" | "activate_request" | "activate_verify"
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const navigate = useNavigate();

  if (!isOpen) return null;

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    const cleanId = identifier.trim();
    const cleanPass = password.trim();
    if (!cleanId) {
      setError("Please enter your registered email address or Student ID.");
      return;
    }
    if (!cleanPass) {
      setError("Please enter your account password.");
      return;
    }

    setIsLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      const data = await loginStudent({ identifier: cleanId, password: cleanPass });
      setSuccessMessage(`Welcome back, ${data.student?.full_name || "Student"}!`);
      setTimeout(() => {
        setIsLoading(false);
        onSuccess?.(data);
        onClose();
      }, 500);
    } catch (err) {
      setIsLoading(false);
      const msg = err.message || "";
      if (msg.toLowerCase().includes("activation required") || msg.toLowerCase().includes("does not have a password")) {
        setError(msg);
        // Switch to OTP activation mode
        setMode("activate_request");
      } else {
        setError(msg || "Failed to log in. Please check your credentials.");
      }
    }
  };

  const handleRequestOTPSubmit = async (e) => {
    e.preventDefault();
    const cleanId = identifier.trim();
    if (!cleanId) {
      setError("Please enter your registered email address or Student ID.");
      return;
    }

    setIsLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      const resp = await requestOTP(cleanId);
      setIsLoading(false);
      setMaskedEmail(resp.masked_email || "");
      setSuccessMessage(resp.message || "Verification code sent to your email.");
      setMode("activate_verify");
    } catch (err) {
      setIsLoading(false);
      setError(err.message || "Failed to send verification code. Please check your identifier.");
    }
  };

  const handleVerifyOTPSubmit = async (e) => {
    e.preventDefault();
    const cleanId = identifier.trim();
    const cleanOtp = otp.trim();
    const cleanPass = newPassword.trim();

    if (!/^\d{6}$/.test(cleanOtp)) {
      setError("Please enter the 6-digit verification code sent to your email.");
      return;
    }
    if (!cleanPass || cleanPass.length < 10) {
      setError("New password must be at least 10 characters.");
      return;
    }

    setIsLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      const data = await verifyOTPAndSetPassword({
        identifier: cleanId,
        otp: cleanOtp,
        newPassword: cleanPass,
      });
      setSuccessMessage(`Password set successfully! Welcome, ${data.student?.full_name || "Student"}!`);
      setTimeout(() => {
        setIsLoading(false);
        onSuccess?.(data);
        onClose();
      }, 600);
    } catch (err) {
      setIsLoading(false);
      setError(err.message || "Failed to verify code. Please check and try again.");
    }
  };

  const handleRegisterClick = () => {
    onClose();
    navigate("/profile");
  };

  return (
    <div className="login-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="login-modal-title">
      <div className="login-modal-backdrop" onClick={onClose} />
      <div className="login-modal-card">
        <div className="login-modal-header">
          <div className="login-modal-title-wrap">
            <span className="login-modal-icon">
              <Icon name="user" size={24} />
            </span>
            <div>
              <h2 id="login-modal-title">
                {mode === "login" && "Student Login"}
                {mode === "activate_request" && "Account Activation / Reset"}
                {mode === "activate_verify" && "Verify Code & Set Password"}
              </h2>
              <p className="login-modal-subtitle">
                {mode === "login" && "Access your Document Vault and scholarship recommendations"}
                {mode === "activate_request" && "Enter your Email or Student ID to receive a verification OTP"}
                {mode === "activate_verify" && `Enter the OTP sent to ${maskedEmail || "your email"}`}
              </p>
            </div>
          </div>
          <button
            className="login-modal-close"
            type="button"
            aria-label="Close login dialog"
            onClick={onClose}
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        {error && (
          <div className="login-modal-alert login-modal-error" role="alert" style={{ margin: "1rem 1.5rem 0" }}>
            <span>{error}</span>
          </div>
        )}

        {successMessage && (
          <div className="login-modal-alert login-modal-success" role="status" style={{ margin: "1rem 1.5rem 0" }}>
            <span>{successMessage}</span>
          </div>
        )}

        {/* 1. LOGIN FORM */}
        {mode === "login" && (
          <form onSubmit={handleLoginSubmit} className="login-modal-form">
            <label className="login-modal-field">
              <span className="field-label">Email Address or Student ID</span>
              <input
                type="text"
                className="login-input"
                placeholder="e.g. student@example.com or Student ID"
                value={identifier}
                onChange={(e) => {
                  setIdentifier(e.target.value);
                  setError("");
                }}
                disabled={isLoading}
                autoFocus
                required
              />
            </label>

            <label className="login-modal-field">
              <span className="field-label">Password</span>
              <input
                type="password"
                className="login-input"
                placeholder="Enter your account password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError("");
                }}
                disabled={isLoading}
                required
              />
            </label>

            <div className="login-modal-actions">
              <button
                type="submit"
                className="login-submit-btn"
                disabled={isLoading || !identifier.trim() || !password.trim()}
              >
                {isLoading ? "Signing in…" : "Sign In to Vault"}
              </button>
            </div>

            <div className="login-modal-footer">
              <p>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setError("");
                    setSuccessMessage("");
                    setMode("activate_request");
                  }}
                >
                  Activate Account or Reset Password
                </button>
              </p>
              <p>
                New to Schobot?{" "}
                <button
                  type="button"
                  className="link-button"
                  onClick={handleRegisterClick}
                >
                  Register your profile
                </button>
              </p>
            </div>
          </form>
        )}

        {/* 2. ACTIVATE / RESET REQUEST FORM */}
        {mode === "activate_request" && (
          <form onSubmit={handleRequestOTPSubmit} className="login-modal-form">
            <label className="login-modal-field">
              <span className="field-label">Email Address or Student ID</span>
              <input
                type="text"
                className="login-input"
                placeholder="e.g. student@example.com or Student ID"
                value={identifier}
                onChange={(e) => {
                  setIdentifier(e.target.value);
                  setError("");
                }}
                disabled={isLoading}
                autoFocus
                required
              />
              <small className="field-help">
                A 6-digit one-time verification code will be sent to your registered email address.
              </small>
            </label>

            <div className="login-modal-actions">
              <button
                type="submit"
                className="login-submit-btn"
                disabled={isLoading || !identifier.trim()}
              >
                {isLoading ? "Sending OTP…" : "Send Verification Code"}
              </button>
            </div>

            <div className="login-modal-footer">
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setError("");
                  setSuccessMessage("");
                  setMode("login");
                }}
              >
                ← Back to Sign In
              </button>
            </div>
          </form>
        )}

        {/* 3. ACTIVATE / RESET VERIFY FORM */}
        {mode === "activate_verify" && (
          <form onSubmit={handleVerifyOTPSubmit} className="login-modal-form">
            <label className="login-modal-field">
              <span className="field-label">6-Digit Verification Code (OTP)</span>
              <input
                type="text"
                className="login-input"
                placeholder="Enter 6-digit code"
                value={otp}
                maxLength={6}
                onChange={(e) => {
                  setOtp(e.target.value.replace(/\D/g, "").slice(0, 6));
                  setError("");
                }}
                inputMode="numeric"
                pattern="[0-9]{6}"
                disabled={isLoading}
                autoFocus
                required
              />
            </label>

            <label className="login-modal-field">
              <span className="field-label">New Password (min 10 characters)</span>
              <input
                type="password"
                className="login-input"
                placeholder="Min 10 characters"
                value={newPassword}
                minLength={10}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  setError("");
                }}
                disabled={isLoading}
                required
              />
            </label>

            <div className="login-modal-actions">
              <button
                type="submit"
                className="login-submit-btn"
                disabled={isLoading || !otp.trim() || !newPassword.trim()}
              >
                {isLoading ? "Verifying…" : "Set Password & Sign In"}
              </button>
            </div>

            <div className="login-modal-footer">
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setError("");
                  setSuccessMessage("");
                  setMode("activate_request");
                }}
              >
                ← Resend Code / Change Identifier
              </button>
              {" · "}
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setError("");
                  setSuccessMessage("");
                  setMode("login");
                }}
              >
                Back to Sign In
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
