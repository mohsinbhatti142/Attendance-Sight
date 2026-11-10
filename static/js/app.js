// static/js/app.js
const { useState, useEffect, useRef } = React;
const SAVED_USERNAME_KEY = "attendsight.saved_username";

function getSavedUsername() {
  try {
    return window.localStorage.getItem(SAVED_USERNAME_KEY) || "";
  } catch (error) {
    console.warn("Could not read the saved administrator username.", error);
    return "";
  }
}

function saveUsername(username) {
  try {
    window.localStorage.setItem(SAVED_USERNAME_KEY, username);
  } catch (error) {
    console.warn("Could not save the administrator username on this device.", error);
  }
}

function announceAttendanceGreeting(employeeName) {
  if (!employeeName || !("speechSynthesis" in window)) return;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  try {
    window.speechSynthesis.cancel();
    const message = new SpeechSynthesisUtterance(`${greeting}, ${employeeName}. Welcome to Attendance-Sight.`);
    message.lang = "en-US";
    message.rate = 0.95;
    message.pitch = 1;
    window.speechSynthesis.speak(message);
  } catch (error) {
    console.warn("Voice greeting is unavailable in this browser.", error);
  }
}

function App() {
  const [activeTab, setActiveTab] = useState("kiosk");

  // Telemetry & Feed state
  const [fps, setFps] = useState(0.0);
  const [totalEnrolled, setTotalEnrolled] = useState(0);
  const [todayPresent, setTodayPresent] = useState(0);
  const [lateArrivals, setLateArrivals] = useState(0);
  const [recentEvents, setRecentEvents] = useState([]);
  const [systemStatus, setSystemStatus] = useState({
    camera_active: false,
    model_ready: false,
    ai_status: "starting",
    model_provider: "unavailable",
  });
  const [shiftPolicy, setShiftPolicy] = useState(null);
  const [admin, setAdmin] = useState(null);
  const [savedUsername, setSavedUsername] = useState(getSavedUsername);
  const [authReady, setAuthReady] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [authNotice, setAuthNotice] = useState("");
  const [authMode, setAuthMode] = useState("signin");
  const [loginError, setLoginError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [setupModalOpen, setSetupModalOpen] = useState(false);
  const [setupDismissed, setSetupDismissed] = useState(false);
  const [accountModalOpen, setAccountModalOpen] = useState(false);

  // Modals
  const [enrollModalOpen, setEnrollModalOpen] = useState(false);
  const [cctvModalOpen, setCctvModalOpen] = useState(false);
  const [selectedCardEmployee, setSelectedCardEmployee] = useState(null);
  const lastGreetedEventRef = useRef(null);


  useEffect(() => {
    Promise.all([
      fetch("/api/v1/auth/me"),
      fetch("/api/v1/auth/setup-status"),
    ]).then(async ([sessionResponse, setupResponse]) => {
      if (sessionResponse.ok) setAdmin(await sessionResponse.json());
      if (!setupResponse.ok) throw new Error("Could not read the initial account setup status.");
      const setup = await setupResponse.json();
      setSetupRequired(!!setup.setup_required);
      setEmailConfigured(!!setup.email_configured);
    }).catch((error) => {
      console.error("Could not check the local account setup status.", error);
      setLoginError("Could not connect to Attendance-Sight. Please restart the app and try again.");
    }).finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    if (!admin) return;
    Promise.all([
      fetch("/api/v1/attendance/shift_policy").then((response) => response.ok ? response.json() : null),
      fetch("/api/v1/stream/camera_source").then((response) => response.ok ? response.json() : null),
    ]).then(([shift, camera]) => {
      if (shift) setShiftPolicy(shift);
      if ((!shift?.configured || !camera?.configured) && !setupDismissed) setSetupModalOpen(true);
    }).catch((error) => console.error("Could not check camera and shift setup.", error));
  }, [admin, setupDismissed]);

  const signIn = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoginBusy(true);
    setLoginError("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: form.get("email"), password: form.get("password") }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Sign-in failed");
      const username = form.get("email");
      saveUsername(username);
      setSavedUsername(username);
      setAdmin(data);
    } catch (error) { setLoginError(error.message); }
    finally { setLoginBusy(false); }
  };

  const registerFirstAdmin = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("confirm_password")) {
      setLoginError("The passwords do not match.");
      return;
    }
    setLoginBusy(true);
    setLoginError("");
    try {
      const response = await fetch("/api/v1/auth/register-first-admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Account setup failed.");
      const username = data.email;
      saveUsername(username);
      setSavedUsername(username);
      setSetupRequired(false);
      setAuthNotice("");
      setAuthMode("signin");
      setAdmin(data);
    } catch (error) {
      setLoginError(error.message);
    } finally {
      setLoginBusy(false);
    }
  };

  const sendAuthCode = async (endpoint, email, successMessage) => {
    setLoginError("");
    setAuthNotice("");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not send the verification code.");
      setAuthNotice(data.message || successMessage);
      return true;
    } catch (error) {
      setLoginError(error.message);
      return false;
    }
  };

  const resetPassword = async (body) => {
    setLoginBusy(true);
    setLoginError("");
    setAuthNotice("");
    try {
      if (body.new_password.length < 10) throw new Error("Use a password with at least 10 characters.");
      const response = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Password reset failed.");
      setAuthNotice(data.message);
      setAuthMode("signin");
    } catch (error) {
      setLoginError(error.message);
    } finally {
      setLoginBusy(false);
    }
  };

  // Poll or WebSocket Telemetry
  useEffect(() => {
    let ws = null;
    let pollInterval = null;

    try {
      const loc = window.location;
      const wsProtocol = loc.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${wsProtocol}//${loc.host}/api/v1/stream/ws`;

      ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setSystemStatus({
            camera_active: !!data.camera_active,
            model_ready: !!data.model_ready,
            ai_status: data.ai_status || "starting",
            model_provider: data.model_provider || "unavailable",
          });
          if (data.fps !== undefined) setFps(data.fps);
        } catch (e) {
          console.error("WS Parse error:", e);
        }
      };

      ws.onerror = () => {
        startPolling();
      };
    } catch (e) {
      startPolling();
    }

    function startPolling() {
      if (pollInterval) return;
      pollInterval = setInterval(fetchLiveStatus, 2500);
    }

    async function fetchLiveStatus() {
      try {
        const res = await fetch("/api/v1/stream/live_status");
        if (res.ok) {
          const data = await res.json();
          setSystemStatus({
            camera_active: !!data.camera_active,
            model_ready: !!data.model_ready,
            ai_status: data.ai_status || "starting",
            model_provider: data.model_provider || "unavailable",
          });
          if (data.fps !== undefined) setFps(data.fps);
          if (data.total_enrolled !== undefined) setTotalEnrolled(data.total_enrolled);
          if (data.today_present !== undefined) setTodayPresent(data.today_present);
          if (data.greeting_event && data.greeting_event.event_id !== lastGreetedEventRef.current) {
            lastGreetedEventRef.current = data.greeting_event.event_id;
            announceAttendanceGreeting(data.greeting_event.name);
          }
          fetch("/api/v1/attendance/dashboard_kpis").then(r => r.ok ? r.json() : null).then(k => { if (k) setLateArrivals(k.late_arrivals || 0); }).catch(() => {});
          if (data.events) {
            setRecentEvents(data.events);
          }
        }
      } catch (e) {
        // ignore network jitter
      }
    }

    fetchLiveStatus();
    startPolling();

    return () => {
      if (ws) ws.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, []);

  if (!authReady) return <div className="min-h-screen grid place-items-center bg-slate-950 text-slate-300">Loading secure workspace…</div>;
  if (!admin) return (
    <window.AuthScreen
      authMode={authMode}
      setAuthMode={(mode) => { setAuthMode(mode); setLoginError(""); setAuthNotice(""); }}
      savedUsername={savedUsername}
      setupRequired={setupRequired}
      emailConfigured={emailConfigured}
      loginError={loginError}
      authNotice={authNotice}
      loginBusy={loginBusy}
      onSignIn={signIn}
      onRegister={registerFirstAdmin}
      onSendPasswordResetCode={(email) => sendAuthCode("/api/v1/auth/send-password-reset-code", email, "If a verified administrator email matches, a password-reset code has been sent.")}
      onResetPassword={resetPassword}
    />
  );

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Navbar */}
      <window.Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        totalEnrolled={totalEnrolled}
        adminUsername={admin.username}
        onOpenSetup={() => { setSetupDismissed(true); setSetupModalOpen(true); }}
        onOpenAccount={() => setAccountModalOpen(true)}
        onLogout={async () => { await fetch("/api/v1/auth/logout", {method:"POST"}); setAdmin(null); setAuthMode("signin"); setSetupModalOpen(false); setSetupDismissed(false); }}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "kiosk" && (
          <window.KioskSplitScreen
            fps={fps}
            totalEnrolled={totalEnrolled}
            todayPresent={todayPresent}
            lateArrivals={lateArrivals}
            recentEvents={recentEvents}
            cameraActive={systemStatus.camera_active}
            modelReady={systemStatus.model_ready}
            aiStatus={systemStatus.ai_status}
            modelProvider={systemStatus.model_provider}
            shiftPolicy={shiftPolicy}
            onOpenEnrollModal={() => setEnrollModalOpen(true)}
            onOpenCctvModal={() => setCctvModalOpen(true)}
          />
        )}

        {activeTab === "employees" && (
          <window.EmployeeDirectory onOpenEnrollModal={() => setEnrollModalOpen(true)} />
        )}

        {activeTab === "payroll" && (
          <window.PayrollSummary
            onViewCard={(empId, name, code) =>
              setSelectedCardEmployee({ id: empId, name, code })
            }
          />
        )}

        {activeTab === "daily" && <window.DailyRecords />}
        {activeTab === "rules" && <window.ShiftRules onOpenCctv={() => setCctvModalOpen(true)} onPolicyChange={setShiftPolicy} cameraActive={systemStatus.camera_active} />}
      </main>

      {/* Modals */}
      <window.MultiStepEnrollModal
        isOpen={enrollModalOpen}
        onClose={() => setEnrollModalOpen(false)}
        onEnrollComplete={() => {
          fetch("/api/v1/stream/live_status")
            .then((r) => r.json())
            .then((d) => {
              if (d.total_enrolled !== undefined) setTotalEnrolled(d.total_enrolled);
            });
        }}
      />

      <window.CctvConfigModal
        isOpen={cctvModalOpen}
        onClose={() => setCctvModalOpen(false)}
      />

      <window.SetupWizard
        isOpen={setupModalOpen}
        onClose={() => { setSetupDismissed(true); setSetupModalOpen(false); }}
        onSaved={(shift) => setShiftPolicy(shift)}
      />

      <window.AccountSettingsModal
        isOpen={accountModalOpen}
        email={admin.email}
        emailVerified={admin.email_verified}
        emailConfigured={emailConfigured}
        onClose={() => setAccountModalOpen(false)}
        onEmailUpdated={(data) => {
          saveUsername(data.email);
          setSavedUsername(data.email);
          setAdmin((current) => ({ ...current, username: data.email, ...data }));
        }}
        onEmailConfigured={() => setEmailConfigured(true)}
      />

      <window.AttendanceCardModal
        employee={selectedCardEmployee}
        onClose={() => setSelectedCardEmployee(null)}
      />
    </div>
  );
}

// Render into DOM
const rootEl = document.getElementById("root");
if (rootEl) {
  const root = ReactDOM.createRoot(rootEl);
  root.render(<App />);
}
