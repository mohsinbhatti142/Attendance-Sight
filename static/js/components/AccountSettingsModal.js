window.AccountSettingsModal = function AccountSettingsModal({
  isOpen,
  email,
  emailVerified,
  emailConfigured,
  onClose,
  onEmailUpdated,
  onEmailConfigured,
}) {
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [recoveryEmail, setRecoveryEmail] = React.useState(email || "");
  const [emailCode, setEmailCode] = React.useState("");
  const [senderEmail, setSenderEmail] = React.useState("");
  const [appPassword, setAppPassword] = React.useState("");
  const [emailBusy, setEmailBusy] = React.useState(false);
  const [emailError, setEmailError] = React.useState("");
  const [emailMessage, setEmailMessage] = React.useState("");

  React.useEffect(() => {
    if (isOpen) {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setRecoveryEmail(email || "");
      setEmailCode("");
      setSenderEmail("");
      setAppPassword("");
      setError("");
      setMessage("");
      setEmailError("");
      setEmailMessage("");
    }
  }, [isOpen, email]);

  if (!isOpen) return null;

  const save = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    if (newPassword && newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      const response = await fetch("/api/v1/auth/account", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword || null,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not update your account.");
      setMessage("Account settings saved.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const sendRecoveryCode = async () => {
    setEmailBusy(true);
    setEmailError("");
    setEmailMessage("");
    try {
      const response = await fetch("/api/v1/auth/account/email/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: recoveryEmail }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not send the verification code.");
      setEmailMessage(data.message);
    } catch (requestError) {
      setEmailError(requestError.message);
    } finally {
      setEmailBusy(false);
    }
  };

  const verifyRecoveryEmail = async () => {
    setEmailBusy(true);
    setEmailError("");
    setEmailMessage("");
    try {
      const response = await fetch("/api/v1/auth/account/email/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: recoveryEmail, code: emailCode }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not verify this email.");
      onEmailUpdated(data);
      setEmailMessage("Recovery email verified.");
      setEmailCode("");
    } catch (requestError) {
      setEmailError(requestError.message);
    } finally {
      setEmailBusy(false);
    }
  };

  const configureSender = async (event) => {
    event.preventDefault();
    setEmailBusy(true);
    setEmailError("");
    setEmailMessage("");
    try {
      const response = await fetch("/api/v1/auth/configure-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender_email: senderEmail, app_password: appPassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not configure Gmail delivery.");
      onEmailConfigured(data.sender_email);
      setEmailMessage("Gmail delivery is ready on this computer.");
      setAppPassword("");
    } catch (requestError) {
      setEmailError(requestError.message);
    } finally {
      setEmailBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <section role="dialog" aria-modal="true" aria-labelledby="account-settings-title" className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <header className="flex items-start justify-between border-b border-slate-100 p-5">
          <div><p className="text-xs font-semibold uppercase tracking-widest text-sky-700">Administrator</p><h2 id="account-settings-title" className="mt-1 text-lg font-bold text-slate-900">Account settings</h2></div>
          <button type="button" onClick={onClose} aria-label="Close account settings" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"><i data-lucide="x" className="h-5 w-5"></i></button>
        </header>
        <form onSubmit={save} className="space-y-4 p-5">
          <div className="rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">Sign-in email: <strong className="text-slate-800">{email}</strong>. This email is also your username. Change it in the verified email section below.</div>
          <label className="block text-xs font-medium text-slate-600">Current password
            <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required autoComplete="current-password" className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
          </label>
          <label className="block text-xs font-medium text-slate-600">New password <span className="font-normal text-slate-400">(leave blank to keep current)</span>
            <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength="10" maxLength="128" autoComplete="new-password" className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
          </label>
          {newPassword && <label className="block text-xs font-medium text-slate-600">Confirm new password
            <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength="10" maxLength="128" autoComplete="new-password" className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
          </label>}
          {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
          {message && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <button type="button" onClick={onClose} className="rounded-xl px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50">Close</button>
            <button disabled={saving} className="rounded-xl bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60">{saving ? "Saving…" : "Save account"}</button>
          </div>
        </form>
        <section className="space-y-3 border-t border-slate-100 p-5">
          <div><h3 className="text-sm font-semibold text-slate-900">Sign-in & recovery email</h3><p className="mt-1 text-xs text-slate-500">{emailVerified ? "This verified email is your username and is used for password recovery." : "Verify an email address to use it as your username and for password recovery."}</p></div>
          <div className="flex gap-2"><input type="email" value={recoveryEmail} onChange={(event) => setRecoveryEmail(event.target.value)} required maxLength="255" autoComplete="email" className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2.5 text-sm" placeholder="you@gmail.com"/><button type="button" disabled={emailBusy || !emailConfigured} onClick={sendRecoveryCode} className="shrink-0 rounded-xl border border-sky-200 px-3 py-2 text-xs font-semibold text-sky-700 disabled:opacity-50">{emailBusy ? "Sending…" : "Send code"}</button></div>
          <div className="flex gap-2"><input value={emailCode} onChange={(event) => setEmailCode(event.target.value)} inputMode="numeric" pattern="[0-9]{6}" maxLength="6" className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2.5 text-sm" placeholder="6-digit code"/><button type="button" disabled={emailBusy || !emailCode} onClick={verifyRecoveryEmail} className="shrink-0 rounded-xl bg-sky-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">Verify email</button></div>
        </section>
        <form onSubmit={configureSender} className="space-y-3 border-t border-slate-100 p-5">
          <div><h3 className="text-sm font-semibold text-slate-900">{emailConfigured ? "Gmail sender settings" : "Set up Gmail delivery"}</h3><p className="mt-1 text-xs text-slate-500">The App Password is encrypted and saved on this computer. Do not use your normal Gmail password.</p></div>
          <input type="email" value={senderEmail} onChange={(event) => setSenderEmail(event.target.value)} required autoComplete="email" className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" placeholder="sender@gmail.com"/>
          <input type="password" value={appPassword} onChange={(event) => setAppPassword(event.target.value)} required minLength="16" maxLength="19" autoComplete="new-password" className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" placeholder="16-character Gmail App Password"/>
          <button disabled={emailBusy} className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50">{emailBusy ? "Checking Gmail…" : "Verify and save sender"}</button>
        </form>
        {(emailError || emailMessage) && <div className="px-5 pb-5">{emailError ? <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{emailError}</p> : <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{emailMessage}</p>}</div>}
      </section>
    </div>
  );
};
