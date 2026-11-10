// static/js/components/AttendanceCardModal.js
window.AttendanceCardModal = function AttendanceCardModal({ employee, onClose }) {
  if (!employee) return null;

  const [details, setDetails] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    async function fetchCard() {
      try {
        setLoading(true);
        const res = await fetch(`/api/v1/attendance/employee_card/${employee.id}`);
        const data = await res.json();
        setDetails({ ...data, attendance_history: (data.audit_trail || []).map((row) => ({ time: row.timestamp, type: row.event_type, confidence: parseFloat(row.confidence) / 100, snapshot: row.snapshot_url })) });
      } catch (e) {
        console.error("Error fetching card details:", e);
      } finally {
        setLoading(false);
      }
    }
    fetchCard();
  }, [employee]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
      <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-xl overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center space-x-3.5">
            <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-700 font-bold text-lg">
              {employee.name ? employee.name.charAt(0).toUpperCase() : "E"}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-slate-900">{employee.name}</h3>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-indigo-600 font-semibold border border-slate-200">
                  {employee.code}
                </span>
              </div>
              <p className="text-xs text-slate-500">Photographic Attendance Card & Liveness Audit</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <i data-lucide="x" className="w-5 h-5"></i>
          </button>
        </div>

        {/* Card Body */}
        <div className="p-6 space-y-5">
          {loading ? (
            <div className="py-12 text-center text-slate-400 text-xs">Loading audit card...</div>
          ) : (
            <>
              {/* Today Status Row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                    Today's Punch Status
                  </span>
                  <div className="mt-2 flex items-center space-x-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span className={`text-sm font-bold ${details?.today?.status === "PRESENT" ? "text-emerald-700" : "text-slate-500"}`}>{details?.today?.status || "UNKNOWN"} · {details?.today?.late_text || ""}</span>
                  </div>
                  <div className="mt-2 text-xs font-mono text-slate-500">
                    Shift Window: <span className="text-slate-800 font-medium">09:00 AM - 06:00 PM</span>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                    Attendance record
                  </span>
                  <div className="mt-2 flex items-center space-x-2">
                    <i data-lucide="shield-check" className="w-4 h-4 text-emerald-600"></i>
                    <span className="text-sm font-bold text-slate-900">{details?.audit_trail?.[0] ? "Attendance event recorded" : "No verification event"}</span>
                  </div>
                  <div className="mt-2 text-xs font-mono text-slate-500">
                    Engine: <span className="text-slate-800 font-medium">Attendance record</span>
                  </div>
                </div>
              </div>

              {/* Recent Punches & Photographic Proof */}
              <div>
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5">
                  Recent attendance and check-in photos
                </h4>
                <div className="rounded-xl border border-slate-200 bg-white overflow-hidden divide-y divide-slate-100 max-h-56 overflow-y-auto shadow-inner">
                  {details && details.attendance_history && details.attendance_history.length > 0 ? (
                    details.attendance_history.map((h, i) => (
                      <div key={i} className="p-3 flex items-center justify-between text-xs hover:bg-slate-50">
                        <div className="flex items-center space-x-3">
                          {h.snapshot ? (
                            <img
                              src={h.snapshot}
                              alt="Audit"
                              className="w-10 h-10 rounded-lg object-cover border border-slate-200 shadow-sm"
                            />
                          ) : (
                            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-400">
                              <i data-lucide="user" className="w-4 h-4"></i>
                            </div>
                          )}
                          <div>
                            <div className="font-mono font-bold text-slate-900">{h.time || h.timestamp}</div>
                            <div className="text-[11px] text-slate-500">{h.date}</div>
                          </div>
                        </div>

                        <div className="text-right">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {h.type || "CHECK_IN"}
                          </span>
                          <div className="text-[11px] font-mono text-emerald-600 font-semibold mt-1">
                            Match: {Math.round((h.confidence || 0.9) * 100)}%
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-6 text-center text-slate-400 text-xs">No punches recorded yet.</div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Close */}
          <div className="pt-2 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors"
            >
              Close Card
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
