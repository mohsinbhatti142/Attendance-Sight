// static/js/components/PayrollSummary.js
window.PayrollSummary = function PayrollSummary({ onViewCard }) {
  const [employees, setEmployees] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const now = new Date();
  const [period, setPeriod] = React.useState(`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}`);

  const fetchPayroll = async () => {
    try {
      setLoading(true);
      const [year, month] = period.split("-");
      const res = await fetch(`/api/v1/attendance/monthly_summary?year=${year}&month=${Number(month)}`);
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : (data.employees || []);
        setEmployees(list);
      } else {
        setEmployees([]);
      }
    } catch (e) {
      console.error("Error fetching payroll:", e);
      setEmployees([]);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    fetchPayroll();
  }, [period]);

  const exportCsv = () => {
    if (!employees || employees.length === 0) return;
    const headers = ["Employee Code", "Full Name", "Department", "Designation", "Working Days", "Present Days", "Half Days", "Late Days", "Absent Days", "Total Hours", "Overtime Hours", "Weighted Overtime", "Attendance %"];
    const rows = employees.map((e) => [
      e.employee_code,
      `"${e.employee_name}"`,
      `"${e.department || 'General'}"`,
      `"${e.designation || 'Staff'}"`,
      e.working_days,
      e.present_days,
      e.half_day_days || 0,
      e.late_days,
      e.absent_days,
      e.total_hours || e.total_hours_worked || 0,
      e.overtime_hours || 0,
      e.overtime_credit_hours || 0,
      `${e.attendance_rate}%`,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Payroll_Attendance_Report.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Monthly attendance report</h2>
          <p className="text-xs text-slate-500">Review attendance, work hours, late arrivals, and overtime for each employee.</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-500">Month <input type="month" value={period} onChange={e=>setPeriod(e.target.value)} className="ml-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800" /></label>
          <button
            onClick={fetchPayroll}
            className="px-3.5 py-2 rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold flex items-center space-x-2 transition-all shadow-sm"
          >
            <i data-lucide="rotate-cw" className="w-3.5 h-3.5"></i>
            <span>Recalculate</span>
          </button>

          <button
            onClick={exportCsv}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-sm flex items-center space-x-2 transition-all"
          >
            <i data-lucide="download" className="w-4 h-4"></i>
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="interactive-card rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 uppercase tracking-wider font-mono border-b border-slate-200">
              <tr>
                <th className="px-5 py-3.5">Employee</th>
                <th className="px-5 py-3.5">Department</th>
                <th className="px-5 py-3.5">Working Days</th>
                <th className="px-5 py-3.5">Present</th>
                <th className="px-5 py-3.5">Half Day</th>
                <th className="px-5 py-3.5">Late Arrivals</th>
                <th className="px-5 py-3.5">Absent</th>
                <th className="px-5 py-3.5">Total Hours</th>
                <th className="px-5 py-3.5">Overtime credit</th>
                <th className="px-5 py-3.5">Attendance %</th>
                <th className="px-5 py-3.5 text-right">Attendance card</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {loading ? (
                <tr>
                    <td colSpan="11" className="px-5 py-8 text-center text-slate-400">
                    Computing monthly metrics...
                  </td>
                </tr>
              ) : employees.length === 0 ? (
                <tr>
                    <td colSpan="11" className="px-5 py-8 text-center text-slate-400">
                    No active attendance logs found for this period.
                  </td>
                </tr>
              ) : (
                employees.map((emp) => (
                  <tr key={emp.employee_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="font-bold text-slate-900">{emp.employee_name}</div>
                      <div className="text-[11px] font-mono text-indigo-600 font-semibold">{emp.employee_code}</div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">{emp.department || "General"}</td>
                    <td className="px-5 py-3.5 font-mono">{emp.working_days}</td>
                    <td className="px-5 py-3.5 font-mono text-emerald-600 font-bold">{emp.present_days}</td>
                    <td className="px-5 py-3.5 font-mono text-slate-600">{emp.half_day_days || 0}</td>
                    <td className="px-5 py-3.5 font-mono text-amber-600 font-semibold">{emp.late_days}</td>
                    <td className="px-5 py-3.5 font-mono text-red-500 font-semibold">{emp.absent_days}</td>
                    <td className="px-5 py-3.5 font-mono font-medium">{emp.total_hours || emp.total_hours_worked || 0} hrs</td>
                    <td className="px-5 py-3.5 font-mono font-medium">{emp.overtime_credit_hours || 0} hrs</td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold ${
                          emp.attendance_rate >= 85
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : emp.attendance_rate >= 60
                            ? "bg-amber-50 text-amber-700 border border-amber-200"
                            : "bg-red-50 text-red-700 border border-red-200"
                        }`}
                      >
                        {emp.attendance_rate}%
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={() => onViewCard(emp.employee_id, emp.employee_name, emp.employee_code)}
                        className="px-3 py-1.5 rounded-xl bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white border border-indigo-200 hover:border-indigo-600 text-xs font-semibold transition-all inline-flex items-center space-x-1.5 shadow-sm"
                      >
                        <i data-lucide="id-card" className="w-3.5 h-3.5"></i>
                        <span>View attendance</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
