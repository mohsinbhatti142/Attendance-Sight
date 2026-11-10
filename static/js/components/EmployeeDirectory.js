// static/js/components/EmployeeDirectory.js
window.EmployeeDirectory = function EmployeeDirectory({ onOpenEnrollModal }) {
  const [employees, setEmployees] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState("");
  const [filterDept, setFilterDept] = React.useState("ALL");

  // Edit Modal State
  const [editingEmployee, setEditingEmployee] = React.useState(null);
  const [editForm, setEditForm] = React.useState({
    full_name: "",
    employee_code: "",
    designation: "",
    email: "",
    phone: "",
    is_active: true,
  });
  const [editLoading, setEditLoading] = React.useState(false);
  const [editError, setEditError] = React.useState("");

  const loadEmployees = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/v1/employees/");
      const data = await res.json();
      // Handle both { employees: [...], total: n } and raw array [...]
      const list = data && data.employees ? data.employees : (Array.isArray(data) ? data : []);
      setEmployees(list);
    } catch (e) {
      console.error("Error loading employees:", e);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    loadEmployees();
  }, []);

  // Open Edit Modal
  const handleOpenEdit = (emp) => {
    setEditingEmployee(emp);
    setEditForm({
      full_name: emp.full_name || "",
      employee_code: emp.employee_code || "",
      designation: emp.designation || "",
      email: emp.email || "",
      phone: emp.phone || "",
      is_active: emp.is_active !== false,
    });
    setEditError("");
  };

  // Submit Edit Form
  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingEmployee) return;
    setEditLoading(true);
    setEditError("");

    try {
      const res = await fetch(`/api/v1/employees/${editingEmployee.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: editForm.full_name,
          employee_code: editForm.employee_code,
          designation: editForm.designation,
          email: editForm.email || null,
          phone: editForm.phone || null,
          is_active: editForm.is_active,
        }),
      });

      if (res.ok) {
        const updated = await res.json();
        setEmployees(employees.map((emp) => (emp.id === editingEmployee.id ? { ...emp, ...updated } : emp)));
        setEditingEmployee(null);
      } else {
        const errData = await res.json();
        setEditError(errData.detail || "Failed to update employee details.");
      }
    } catch (err) {
      setEditError("Network error updating employee profile.");
    } finally {
      setEditLoading(false);
    }
  };

  // Delete Employee
  const handleDelete = async (empId, name) => {
    if (!confirm(`Are you sure you want to delete employee "${name}"? This will purge all biometric vectors and historical attendance logs.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/v1/employees/${empId}`, { method: "DELETE" });
      if (res.ok) {
        setEmployees(employees.filter((e) => e.id !== empId));
      } else {
        alert("Failed to delete employee.");
      }
    } catch (e) {
      alert("Network error deleting employee.");
    }
  };

  const filtered = employees.filter((emp) => {
    const matchesSearch =
      emp.full_name?.toLowerCase().includes(search.toLowerCase()) ||
      emp.employee_code?.toLowerCase().includes(search.toLowerCase());
    const matchesDept = filterDept === "ALL" || emp.department?.name === filterDept;
    return matchesSearch && matchesDept;
  });

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Employee Master Directory</h2>
          <p className="text-xs text-slate-500">View, search, edit, and manage registered biometric employee profiles</p>
        </div>

        <button
          onClick={onOpenEnrollModal}
          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm flex items-center space-x-2 transition-all"
        >
          <i data-lucide="user-plus" className="w-4 h-4"></i>
          <span>Add employee</span>
        </button>
      </div>

      {/* Filter / Search Bar */}
      <div className="interactive-card p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-80">
          <i data-lucide="search" className="w-4 h-4 text-slate-400 absolute left-3.5 top-3"></i>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or employee code..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500"
          />
        </div>

        <div className="flex items-center space-x-2 text-xs">
          <span className="text-slate-500 font-medium">Filter Department:</span>
          <select
            value={filterDept}
            onChange={(e) => setFilterDept(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
          >
            <option value="ALL">All Departments</option>
            <option value="Engineering">Engineering</option>
            <option value="Human Resources">Human Resources</option>
            <option value="Operations">Operations</option>
            <option value="Finance">Finance</option>
            <option value="General">General</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="interactive-card rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 uppercase tracking-wider font-mono border-b border-slate-200">
              <tr>
                <th className="px-5 py-3.5">Employee</th>
                <th className="px-5 py-3.5">Code</th>
                <th className="px-5 py-3.5">Department</th>
                <th className="px-5 py-3.5">Designation</th>
                <th className="px-5 py-3.5">Face profile</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {loading ? (
                <tr>
                  <td colSpan="6" className="px-5 py-8 text-center text-slate-400">
                    Loading employee directory...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-5 py-8 text-center text-slate-400">
                    No employees found matching criteria.
                  </td>
                </tr>
              ) : (
                filtered.map((emp) => (
                  <tr key={emp.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-5 py-3.5 flex items-center space-x-3">
                      {emp.profile_image_url ? (
                        <img
                          src={emp.profile_image_url}
                          alt={emp.full_name}
                          className="w-10 h-10 rounded-xl object-cover border border-slate-200 shadow-sm"
                          onError={(event) => { event.currentTarget.style.display = "none"; }}
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-700 font-bold text-sm">
                          {emp.full_name ? emp.full_name.charAt(0).toUpperCase() : "E"}
                        </div>
                      )}
                      <div>
                        <div className="font-bold text-slate-900">{emp.full_name}</div>
                        <div className="text-[11px] text-slate-500">{emp.email || "No email assigned"}</div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-indigo-600 font-semibold">{emp.employee_code}</td>
                    <td className="px-5 py-3.5 text-slate-600">{emp.department?.name || "General"}</td>
                    <td className="px-5 py-3.5 text-slate-600">{emp.designation || "Staff"}</td>
                    <td className="px-5 py-3.5">
                      <span className="px-2.5 py-1 rounded-full text-[11px] font-mono font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {emp.is_active ? "Face profile enrolled" : "Inactive profile"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right space-x-2">
                      <button
                        onClick={() => handleOpenEdit(emp)}
                        className="px-2.5 py-1.5 rounded-lg text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 border border-slate-200 transition-colors inline-flex items-center space-x-1"
                        title="Edit Details"
                      >
                        <i data-lucide="edit-3" className="w-3.5 h-3.5"></i>
                        <span className="font-medium text-[11px]">Edit</span>
                      </button>

                      <button
                        onClick={() => handleDelete(emp.id, emp.full_name)}
                        className="p-2 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 border border-slate-200 transition-colors inline-flex items-center justify-center"
                        title="Delete Profile"
                        aria-label={`Delete ${emp.full_name}`}
                      >
                        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                          <path d="M3 6h18M8 6V4h8v2m3 0-.8 14H5.8L5 6m4 4v6m6-6v6" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* EDIT EMPLOYEE MODAL */}
      {editingEmployee && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-200">
                  <i data-lucide="user-cog" className="w-4 h-4"></i>
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Edit Employee Profile</h3>
                  <p className="text-xs text-slate-500">Update employee details & designation</p>
                </div>
              </div>
              <button
                onClick={() => setEditingEmployee(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                <i data-lucide="x" className="w-5 h-5"></i>
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="p-6 space-y-4">
              {editError && (
                <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-600 flex items-center space-x-2">
                  <i data-lucide="alert-circle" className="w-4 h-4 flex-shrink-0"></i>
                  <span>{editError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name *</label>
                  <input
                    type="text"
                    required
                    value={editForm.full_name}
                    onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500 font-medium"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Employee Code *</label>
                  <input
                    type="text"
                    required
                    value={editForm.employee_code}
                    onChange={(e) => setEditForm({ ...editForm, employee_code: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 font-mono focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Designation</label>
                  <input
                    type="text"
                    value={editForm.designation}
                    onChange={(e) => setEditForm({ ...editForm, designation: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
                  <input
                    type="email"
                    value={editForm.email}
                    onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                    placeholder="email@company.com"
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Phone</label>
                  <input
                    type="text"
                    value={editForm.phone}
                    onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                    placeholder="+92 300 1234567"
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="pt-4 flex items-center justify-end space-x-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditingEmployee(null)}
                  className="px-4 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editLoading}
                  className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all flex items-center space-x-2"
                >
                  <span>{editLoading ? "Saving..." : "Save Changes"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
