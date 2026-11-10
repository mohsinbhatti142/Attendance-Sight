// static/js/components/Navbar.js
window.Navbar = function Navbar({ activeTab, setActiveTab, totalEnrolled, adminUsername, onLogout, onOpenSetup, onOpenAccount }) {
  const [timeStr, setTimeStr] = React.useState("");
  const [dateStr, setDateStr] = React.useState("");
  const [accountMenuOpen, setAccountMenuOpen] = React.useState(false);
  const accountMenuRef = React.useRef(null);

  React.useEffect(() => {
    function updateClock() {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true }));
      setDateStr(now.toLocaleDateString("en-CA"));
    }
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  React.useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(event.target)) {
        setAccountMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, []);

  const adminLabel = adminUsername || "Admin";
  const adminInitial = adminLabel.trim().charAt(0).toUpperCase() || "A";

  const navItems = [
    { id: "kiosk", label: "Live Attendance", icon: "camera" },
    { id: "employees", label: `Employees (${totalEnrolled})`, icon: "users" },
    { id: "daily", label: "Daily Records", icon: "calendar-days" },
    { id: "payroll", label: "Monthly Reports", icon: "file-text" },
    { id: "rules", label: "Shift Rules", icon: "clock-3" },
  ];

  return (
    <header className="border-b border-slate-200/90 bg-white/95 backdrop-blur-md sticky top-0 z-40 shadow-sm">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 min-h-[72px] py-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        {/* Brand */}
        <div className="flex items-center space-x-3">
          <img src="/static/attendance-sight-logo.svg" alt="Attendance-Sight" className="w-40 sm:w-48 h-auto object-contain" />
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                ATTENDANCE
              </span>
            </div>
            <p className="hidden sm:block text-xs text-slate-500">Private, on-device attendance</p>
          </div>
        </div>

        {/* Center Nav Tabs */}
        {/* System HUD Status */}
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2 sm:gap-3">
          {/* Live Clock */}
          <div className="hidden sm:flex items-center space-x-2 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700 font-mono">
            <span className="text-slate-500">{dateStr}</span>
            <span className="text-indigo-600 font-semibold">{timeStr}</span>
          </div>
          <div ref={accountMenuRef} className="relative pl-2 sm:pl-3 sm:border-l border-slate-200">
            <button
              type="button"
              onClick={() => setAccountMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={accountMenuOpen}
              aria-label="Open admin account menu"
              className="flex items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors"
            >
              <span className="w-8 h-8 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-semibold flex items-center justify-center">{adminInitial}</span>
              <span className="hidden sm:flex flex-col items-start leading-tight">
                <span className="text-xs font-medium text-slate-800">{adminLabel}</span>
                <span className="text-[10px] text-slate-500">Administrator</span>
              </span>
              <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className={`w-4 h-4 text-slate-500 transition-transform ${accountMenuOpen ? "rotate-180" : ""}`}>
                <path d="m5 7.5 5 5 5-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {accountMenuOpen && (
              <div role="menu" aria-label="Admin account" className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10 z-50">
                <div className="px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">Signed in as</p>
                  <p className="text-sm font-medium text-slate-800 truncate">{adminLabel}</p>
                </div>
                <div className="my-1 border-t border-slate-100" />
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setAccountMenuOpen(false); onOpenAccount(); }}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
                >
                  <i data-lucide="user-round-cog" className="h-4 w-4"></i>
                  <span>Account settings</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setAccountMenuOpen(false); onOpenSetup(); }}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
                >
                  <i data-lucide="settings-2" className="h-4 w-4"></i>
                  <span>Camera & shift setup</span>
                </button>
                <div className="my-1 border-t border-slate-100" />
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setAccountMenuOpen(false); onLogout(); }}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-rose-50 hover:text-rose-700 transition-colors"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                    <path d="M10 17l5-5-5-5M15 12H3m9-8h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5" />
                  </svg>
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-4 sm:px-6 lg:px-8 py-2 border-t border-slate-100 bg-white">
        <div className="max-w-[1600px] w-full mx-auto flex gap-1">
          {navItems.map(item => <button key={item.id} onClick={() => setActiveTab(item.id)} className={`shrink-0 px-3.5 py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors ${activeTab===item.id?"bg-indigo-50 text-indigo-700":"text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>{item.label}</button>)}
        </div>
      </nav>
    </header>
  );
};
