// static/js/components/MultiStepEnrollModal.js
window.MultiStepEnrollModal = function MultiStepEnrollModal({ isOpen, onClose, onEnrollComplete }) {
  if (!isOpen) return null;
  const SAMPLES_PER_ANGLE = 3;

  const [step, setStep] = React.useState(1);
  const [formData, setFormData] = React.useState({
    fullName: "",
    employeeCode: `EMP-${Math.floor(1000 + Math.random() * 9000)}`,
    department: "Engineering",
    designation: "Software Engineer",
    email: "",
    phone: "",
  });

  const [sessionId, setSessionId] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [statusMsg, setStatusMsg] = React.useState("");
  const [errorMsg, setErrorMsg] = React.useState("");

  // Poses tracked in Step 2: center, left, right
  const [capturedPoses, setCapturedPoses] = React.useState({});
  const [activePoseTarget, setActivePoseTarget] = React.useState("center");
  const [cameraPreviewReady, setCameraPreviewReady] = React.useState(false);

  // Step 1: Submit employee details and start the face capture session
  const handleStartKyc = async (e) => {
    e.preventDefault();
    if (!formData.fullName.trim()) {
      setErrorMsg("Please enter the employee's full name.");
      return;
    }
    setErrorMsg("");
    setLoading(true);

    try {
      const res = await fetch("/api/v1/stream/kyc/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: formData.fullName,
          employee_code: formData.employeeCode,
          department: formData.department,
          designation: formData.designation,
        }),
      });
      const data = await res.json();
      if (res.ok && data.session_id) {
        setSessionId(data.session_id);
        setCapturedPoses({});
        setStep(2);
        setCameraPreviewReady(false);
        setActivePoseTarget("center");
        setStatusMsg("Look straight into the lens for the frontal pose.");
      } else {
        setErrorMsg(data.detail || "Could not start the face capture session.");
      }
    } catch (err) {
      setErrorMsg("Network error connecting to biometric engine.");
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Capture Target Pose
  const handleCapturePose = async (angleKey) => {
    if (!sessionId) return;
    setLoading(true);
    setStatusMsg(`Checking the ${angleKey.toLowerCase()} photo...`);
    setErrorMsg("");

    try {
      const res = await fetch("/api/v1/stream/kyc/sample", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          angle: angleKey,
        }),
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok && data.success) {
        setCapturedPoses((prev) => ({
          ...prev,
          [angleKey]: {
            previewUrl: data.preview_url,
            quality: data.quality,
            sampleCount: data.sample_count,
          },
        }));

        // Collect three clear, slightly varied samples for each head angle.
        if (data.sample_count < SAMPLES_PER_ANGLE) {
          setStatusMsg(`Sample ${data.sample_count}/${SAMPLES_PER_ANGLE} saved. Slightly change your expression or head position, then capture again.`);
        } else if (angleKey === "center") {
          setActivePoseTarget("left");
          setStatusMsg("Center complete. Now turn your head slightly LEFT and capture three varied photos.");
        } else if (angleKey === "left") {
          setActivePoseTarget("right");
          setStatusMsg("Left angle complete. Turn slightly RIGHT and capture three varied photos.");
        } else if (angleKey === "right") {
          setStatusMsg("All nine varied face samples are ready to save.");
          setTimeout(() => setStep(3), 600);
        }
      } else {
        setErrorMsg(data.message || data.detail || "Pose validation failed. Please follow guidance.");
      }
    } catch (err) {
      setErrorMsg("Failed to capture pose from camera feed.");
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Save the employee profile and face photos
  const handleCommitKyc = async () => {
    if (!sessionId) return;
    setLoading(true);
    setErrorMsg("");
    setStatusMsg("Saving face photos and preparing the employee profile...");

    try {
      const res = await fetch("/api/v1/stream/kyc/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json();

      if (data.success) {
        if (onEnrollComplete) onEnrollComplete();
        onClose();
      } else {
        setErrorMsg(data.detail || "Error saving employee biometric profile.");
      }
    } catch (err) {
      setErrorMsg("Network error committing to database.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-900/60 backdrop-blur-sm">
      <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-xl max-h-[calc(100dvh-1.5rem)] overflow-y-auto overscroll-contain shadow-2xl flex flex-col">
        {/* Header */}
        <div className="sticky top-0 z-10 px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-200">
              <i data-lucide="scan" className="w-4 h-4"></i>
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Add an employee face profile</h2>
              <p className="text-xs text-slate-500">Follow the prompts and turn your head when asked.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            type="button"
            aria-label="Close add employee window"
            title="Close"
            className="w-9 h-9 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-200 border border-slate-200 flex items-center justify-center transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="w-5 h-5">
              <path d="m18 6-12 12M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Step Indicator */}
        <div className="px-6 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between text-xs font-mono">
          <div className={`flex items-center space-x-2 ${step === 1 ? "text-indigo-600 font-bold" : "text-slate-400"}`}>
            <span className="w-5 h-5 rounded-full border border-current flex items-center justify-center text-[11px]">1</span>
            <span>Details</span>
          </div>
          <span className="text-slate-300">───</span>
          <div className={`flex items-center space-x-2 ${step === 2 ? "text-indigo-600 font-bold" : "text-slate-400"}`}>
            <span className="w-5 h-5 rounded-full border border-current flex items-center justify-center text-[11px]">2</span>
            <span>Face photos</span>
          </div>
          <span className="text-slate-300">───</span>
          <div className={`flex items-center space-x-2 ${step === 3 ? "text-indigo-600 font-bold" : "text-slate-400"}`}>
            <span className="w-5 h-5 rounded-full border border-current flex items-center justify-center text-[11px]">3</span>
            <span>Index Commit</span>
          </div>
        </div>

        {/* Body Contents by Step */}
        <div className="p-5 sm:p-6">
          {errorMsg && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-600 flex items-center space-x-2">
              <i data-lucide="alert-circle" className="w-4 h-4 flex-shrink-0"></i>
              <span>{errorMsg}</span>
            </div>
          )}

          {/* STEP 1: Details */}
          {step === 1 && (
            <form onSubmit={handleStartKyc} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name *</label>
                  <input
                    type="text"
                    required
                    value={formData.fullName}
                    onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                    placeholder="e.g. Mohsin Ali"
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500 font-medium"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Employee Code *</label>
                  <input
                    type="text"
                    required
                    value={formData.employeeCode}
                    onChange={(e) => setFormData({ ...formData, employeeCode: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 font-mono focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Department</label>
                  <select
                    value={formData.department}
                    onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  >
                    <option value="Engineering">Engineering & Technology</option>
                    <option value="Human Resources">Human Resources</option>
                    <option value="Operations">Operations & Logistics</option>
                    <option value="Finance">Finance & Accounts</option>
                    <option value="General">General Staff</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Designation</label>
                  <input
                    type="text"
                    value={formData.designation}
                    onChange={(e) => setFormData({ ...formData, designation: e.target.value })}
                    placeholder="e.g. AI Vision Specialist"
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Email (Optional)</label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="mohsin@enterprise.com"
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Phone (Optional)</label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    placeholder="+92 300 1234567"
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="pt-4 flex justify-end">
                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all flex items-center space-x-2"
                >
                  <span>Continue to face photos</span>
                  <i data-lucide="arrow-right" className="w-4 h-4"></i>
                </button>
              </div>
            </form>
          )}

          {/* STEP 2: Multi-Angle Calibration */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-950 aspect-video max-h-[28dvh]">
                <img
                  src="/api/v1/stream/video_feed"
                  alt="Live camera preview for employee enrollment"
                  onLoad={() => setCameraPreviewReady(true)}
                  onError={() => { setCameraPreviewReady(false); setErrorMsg("Camera feed is unavailable. Check the selected camera and try again."); }}
                  className="w-full h-full object-contain"
                />
                {!cameraPreviewReady && <div className="absolute inset-0 grid place-items-center text-sm text-white/80">Connecting to the camera…</div>}
                <div className="absolute left-3 top-3 rounded-full bg-black/60 px-3 py-1 text-[11px] font-medium text-white">LIVE ENROLLMENT PREVIEW</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-500">Target Pose:</span>
                  <h4 className="text-sm font-bold text-indigo-600 uppercase tracking-wide">
                    {activePoseTarget} Pose
                  </h4>
                </div>
                <p className="text-xs text-slate-600 font-medium">{statusMsg}</p>
              </div>

              {/* 3 Pose Slots */}
              <div className="grid grid-cols-3 gap-3">
                {["center", "left", "right"].map((poseKey) => {
                  const captured = capturedPoses[poseKey];
                  const isActive = activePoseTarget === poseKey;

                  return (
                    <div
                      key={poseKey}
                      className={`p-3.5 rounded-xl border flex flex-col items-center justify-center transition-all ${
                        captured
                          ? "bg-emerald-50/60 border-emerald-300"
                          : isActive
                          ? "bg-indigo-50/60 border-indigo-400 ring-2 ring-indigo-500/10"
                          : "bg-slate-50 border-slate-200 opacity-60"
                      }`}
                    >
                      <span className="text-[11px] font-mono font-bold uppercase mb-2 text-slate-700">
                        {poseKey}
                      </span>

                      {captured ? (
                        <div className="relative">
                          <img
                            src={captured.previewUrl}
                            alt={poseKey}
                            className="w-16 h-16 rounded-lg object-cover border border-emerald-300 shadow-sm"
                          />
                          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-emerald-600 text-white flex items-center justify-center text-[10px] font-bold">
                            ✓
                          </span>
                        </div>
                      ) : (
                        <div className="w-16 h-16 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-400">
                          <i data-lucide="user" className="w-6 h-6"></i>
                        </div>
                      )}

                      <span className="text-[10px] mt-2 font-mono font-medium text-slate-500">
                        {captured ? `${captured.sampleCount}/${SAMPLES_PER_ANGLE} photos · quality ${captured.quality}` : isActive ? `0/${SAMPLES_PER_ANGLE} photos` : "Pending"}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Action */}
              <div className="pt-4 flex items-center justify-between border-t border-slate-100">
                <button
                  onClick={() => setStep(1)}
                  className="px-3.5 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-800"
                >
                  Back to Details
                </button>

                <button
                  onClick={() => handleCapturePose(activePoseTarget)}
                  disabled={loading || !cameraPreviewReady}
                  className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold shadow-sm flex items-center space-x-2"
                >
                  <i data-lucide="camera" className="w-4 h-4"></i>
                  <span>Capture {activePoseTarget.toUpperCase()} ({(capturedPoses[activePoseTarget]?.sampleCount || 0) + 1}/{SAMPLES_PER_ANGLE})</span>
                </button>
              </div>
            </div>
          )}

          {/* STEP 3: Preview & Commit */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center space-x-2">
                <i data-lucide="check-circle" className="w-4 h-4 text-emerald-600 flex-shrink-0"></i>
                <span className="font-medium">Nine face samples across center, left, and right have been checked. The profile is ready to save.</span>
              </div>

              {/* Summary Profile Preview */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div>
                  <h4 className="text-base font-bold text-slate-900">{formData.fullName}</h4>
                  <p className="text-xs text-slate-500 font-mono">
                    {formData.employeeCode} • {formData.department} ({formData.designation})
                  </p>
                </div>
                <span className="px-2.5 py-1 rounded-full bg-indigo-100 text-indigo-700 font-mono text-xs font-semibold border border-indigo-200">
                  9 Face Samples Ready
                </span>
              </div>

              {/* Action */}
              <div className="pt-4 flex items-center justify-between border-t border-slate-100">
                <button
                  onClick={() => setStep(2)}
                  className="px-3.5 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-800"
                >
                  Recalibrate Poses
                </button>

                <button
                  onClick={handleCommitKyc}
                  disabled={loading}
                  className="px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-sm flex items-center space-x-2"
                >
                  <i data-lucide="database" className="w-4 h-4"></i>
                  <span>Commit & Save Face ID</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
