window.AuthScreen = function AuthScreen({
  authMode,
  setAuthMode,
  savedUsername,
  setupRequired,
  emailConfigured,
  loginError,
  authNotice,
  loginBusy,
  onSignIn,
  onRegister,
  onSendPasswordResetCode,
  onResetPassword,
}) {
  const [actionBusy, setActionBusy] = React.useState(false);

  const runAction = async (action) => {
    setActionBusy(true);
    try {
      return await action();
    } finally {
      setActionBusy(false);
    }
  };

  const submitReset = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (form.elements.new_password.value !== form.elements.confirm_password.value) {
      form.elements.confirm_password.setCustomValidity("The passwords do not match.");
      form.elements.confirm_password.reportValidity();
      return;
    }
    form.elements.confirm_password.setCustomValidity("");
    await runAction(() => onResetPassword({
      email: form.elements.email.value.trim(),
      code: form.elements.code.value.trim(),
      new_password: form.elements.new_password.value,
    }));
  };

  const heading = {
    signin: ["Welcome back", "Sign in to manage your private attendance workspace."],
    register: ["Create your account", "Enter your email and choose a password. Your email will be your username."],
    forgot: ["Reset your password", "Enter your sign-in email, verify the code, then choose a new password."],
  }[authMode];

  return (
    <div className="min-h-screen relative overflow-hidden bg-[#f6fafc] text-slate-800 flex items-center justify-center p-5">
      <div className="absolute inset-0" style={{backgroundImage:"radial-gradient(circle at 8% 8%, #dff5fb 0, transparent 32%), radial-gradient(circle at 95% 90%, #e7f3fa 0, transparent 30%)"}}></div>
      <div className="relative w-full max-w-5xl grid lg:grid-cols-[1.1fr_.9fr] rounded-[28px] overflow-hidden border border-slate-200 bg-white shadow-xl shadow-slate-200/70">
        <section className="hidden lg:flex flex-col justify-between p-12 bg-gradient-to-br from-white via-sky-50 to-cyan-50 border-r border-slate-200">
          <div><img src="/static/attendance-sight-logo.svg" alt="Attendance-Sight" className="w-52 h-auto" />
            <div className="mt-20"><div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-sky-200 bg-white text-sky-700 text-xs"><span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>Private local workspace</div><h1 className="text-4xl font-semibold leading-tight mt-6 text-slate-900">Attendance,<br/><span className="text-sky-600">clear and organized.</span></h1><p className="mt-5 max-w-md text-sm leading-6 text-slate-500">Manage employee records, review daily attendance, and prepare monthly reports.</p></div>
          </div><div className="text-xs text-slate-400 flex items-center justify-between"><span>Attendance-Sight · Local Attendance</span><span className="font-mono">PRIVATE LOCAL WORKSPACE</span></div>
        </section>
        <section className="max-h-[90vh] overflow-y-auto p-7 sm:p-12 flex flex-col justify-center">
          <div className="lg:hidden mb-9"><img src="/static/attendance-sight-logo.svg" alt="Attendance-Sight" className="w-48 h-auto" /></div>
          <div className="text-xs uppercase tracking-[.22em] text-sky-700 font-semibold">Attendance-Sight · Administrator</div>
          <h2 className="text-3xl font-semibold mt-3 text-slate-900">{heading[0]}</h2>
          <p className="text-sm text-slate-500 mt-2 mb-8">{heading[1]}</p>

          {authMode === "signin" && (
            <form onSubmit={onSignIn} className="space-y-5">
              <label className="block"><span className="text-xs text-slate-600 font-medium">Email address</span><div className="relative mt-2"><i data-lucide="user-round" className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400"></i><input name="email" type="email" autoComplete="username" defaultValue={savedUsername} maxLength="254" required className="w-full rounded-xl bg-white border border-slate-200 py-3 pl-11 pr-4 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100" placeholder="Enter your email"/></div></label>
              <label className="block"><span className="text-xs text-slate-600 font-medium">Password</span><div className="relative mt-2"><i data-lucide="key-round" className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400"></i><input name="password" type="password" autoComplete="current-password" maxLength="256" required className="w-full rounded-xl bg-white border border-slate-200 py-3 pl-11 pr-4 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100" placeholder="Enter your password"/></div></label>
              {loginError && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{loginError}</div>}
              {authNotice && <div role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{authNotice}</div>}
              <button disabled={loginBusy} className="w-full rounded-xl bg-sky-600 hover:bg-sky-700 disabled:opacity-60 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-900/10 transition-colors flex justify-center items-center gap-2">{loginBusy ? "Signing in…" : "Sign in"}<i data-lucide="arrow-right" className="h-4 w-4"></i></button>
              <div className="text-right"><button type="button" onClick={() => setAuthMode("forgot")} className="text-sm font-medium text-sky-700 hover:text-sky-900">Forgot password?</button></div>
            </form>
          )}

          {authMode === "register" && (
            <form key="register" onSubmit={onRegister} className="space-y-4">
              <label className="block"><span className="text-xs text-slate-600 font-medium">Email address (your username)</span><input name="email" type="email" autoComplete="email" maxLength="254" required className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100" placeholder="you@gmail.com"/></label>
              <label className="block"><span className="text-xs text-slate-600 font-medium">Create password</span><input name="password" type="password" autoComplete="new-password" minLength="10" maxLength="128" required className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" placeholder="At least 10 characters"/></label>
              <label className="block"><span className="text-xs text-slate-600 font-medium">Confirm password</span><input name="confirm_password" type="password" autoComplete="new-password" minLength="10" maxLength="128" required className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" placeholder="Enter it again"/></label>
              {loginError && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{loginError}</div>}
              {authNotice && <div role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{authNotice}</div>}
              <div className="rounded-xl bg-sky-50 p-3 text-xs leading-5 text-sky-800">Your account is created on this computer. To enable email password recovery, verify your address and set up email delivery later in Account Settings.</div>
              <button disabled={loginBusy} className="w-full rounded-xl bg-sky-600 py-3 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60">{loginBusy ? "Creating account…" : "Create account"}</button>
            </form>
          )}

          {authMode === "forgot" && (
            <form key="forgot" onSubmit={submitReset} className="space-y-4">
              <label className="block"><span className="text-xs text-slate-600 font-medium">Your sign-in email</span><input name="email" type="email" autoComplete="email" required className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" placeholder="you@gmail.com"/></label>
              <div className="flex gap-2"><input name="code" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" required className="min-w-0 flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm" placeholder="6-digit email code"/><button type="button" disabled={actionBusy || !emailConfigured} onClick={(event) => { event.preventDefault(); const email = event.currentTarget.form.elements.email.value.trim(); if (email) runAction(() => onSendPasswordResetCode(email)); }} className="shrink-0 rounded-xl border border-sky-200 px-3 py-2 text-xs font-semibold text-sky-700 hover:bg-sky-50 disabled:opacity-50">{actionBusy ? "Sending…" : "Send code"}</button></div>
              {!emailConfigured && <div className="rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-800">Email recovery is not set up on this computer. If you can sign in, configure Gmail delivery and verify your email in Account Settings first.</div>}
              <label className="block"><span className="text-xs text-slate-600 font-medium">New password</span><input name="new_password" type="password" autoComplete="new-password" minLength="10" maxLength="128" required className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" placeholder="At least 10 characters"/></label>
              <label className="block"><span className="text-xs text-slate-600 font-medium">Confirm new password</span><input name="confirm_password" type="password" autoComplete="new-password" minLength="10" maxLength="128" required onChange={(event) => event.currentTarget.setCustomValidity("")} className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" placeholder="Enter it again"/></label>
              {loginError && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{loginError}</div>}
              {authNotice && <div role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{authNotice}</div>}
              <button disabled={loginBusy || !emailConfigured} className="w-full rounded-xl bg-sky-600 py-3 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60">{loginBusy ? "Resetting password…" : "Reset password"}</button>
            </form>
          )}

          {authMode === "signin" && setupRequired && (
            <p className="mt-5 text-center text-sm text-slate-500">Don't have an account yet?{" "}
              <button type="button" onClick={() => setAuthMode("register")} className="font-semibold text-sky-700 hover:text-sky-900">Register</button>
            </p>
          )}
          {authMode !== "signin" && <button type="button" onClick={() => { setAuthMode("signin"); }} className="mt-4 w-full text-center text-sm font-medium text-sky-700 hover:text-sky-900">Back to sign in</button>}
          <div className="mt-7 border-t border-slate-100 pt-5 flex items-center gap-2 text-xs text-slate-500"><i data-lucide="shield-check" className="w-4 h-4 text-emerald-600"></i>{authMode === "register" ? "Email codes expire after 10 minutes." : "Secure sign-in for your local workspace."}</div>
        </section>
      </div>
    </div>
  );
};
