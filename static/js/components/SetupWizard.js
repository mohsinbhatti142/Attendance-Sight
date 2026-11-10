window.SetupWizard = function SetupWizard({ isOpen, onClose, onSaved }) {
  const defaultShift = {
    name: "Standard shift",
    start_time: "09:00",
    end_time: "18:00",
    grace_minutes: 15,
    work_days: [0, 1, 2, 3, 4],
    half_day_hours: 4,
    overtime_after_hours: 9,
    overtime_multiplier: 1.5,
  };
  const [form, setForm] = React.useState(defaultShift);
  const [sourceType, setSourceType] = React.useState("none");
  const [cameraConfigured, setCameraConfigured] = React.useState(false);
  const [webcamIndex, setWebcamIndex] = React.useState("");
  const [rtspUrl, setRtspUrl] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");

  React.useEffect(() => {
    if (!isOpen) return;
    let active = true;
    Promise.all([
      fetch("/api/v1/attendance/shift_policy").then(async (response) => {
        if (!response.ok) throw new Error("Could not load shift settings.");
        return response.json();
      }),
      fetch("/api/v1/stream/camera_source").then(async (response) => {
        if (!response.ok) throw new Error("Could not load camera settings.");
        return response.json();
      }),
    ]).then(([shift, camera]) => {
      if (!active) return;
      setForm({ ...defaultShift, ...shift });
      setCameraConfigured(!!camera.configured);
      if (camera.source !== null && camera.source !== undefined) {
        const source = String(camera.source);
        if (/^\d+$/.test(source)) {
          setSourceType("webcam");
          setWebcamIndex(source);
        } else {
          setSourceType("rtsp");
          setRtspUrl(source);
        }
      } else {
        setSourceType("none");
        setWebcamIndex("");
        setRtspUrl("");
      }
    }).catch((loadError) => {
      if (active) setError(loadError.message);
    });
    return () => { active = false; };
  }, [isOpen]);

  if (!isOpen) return null;

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const toggleDay = (day) => set(
    "work_days",
    form.work_days.includes(day)
      ? form.work_days.filter((value) => value !== day)
      : [...form.work_days, day].sort(),
  );
  const save = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const shiftResponse = await fetch("/api/v1/attendance/shift_policy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          grace_minutes: Number(form.grace_minutes),
          half_day_hours: Number(form.half_day_hours),
          overtime_after_hours: Number(form.overtime_after_hours),
          overtime_multiplier: Number(form.overtime_multiplier),
        }),
      });
      const shift = await shiftResponse.json();
      if (!shiftResponse.ok) {
        throw new Error(typeof shift.detail === "string" ? shift.detail : "Please review the shift settings.");
      }

      let cameraIsConfigured = cameraConfigured;
      if (sourceType === "webcam" || sourceType === "rtsp") {
        const source = sourceType === "webcam" ? webcamIndex : rtspUrl.trim();
        if (!source) throw new Error("Select a webcam or enter a network camera address.");
        const cameraResponse = await fetch(
          `/api/v1/stream/set_camera_source?source=${encodeURIComponent(source)}`,
          { method: "POST" },
        );
        const camera = await cameraResponse.json();
        if (!cameraResponse.ok) {
          throw new Error(typeof camera.detail === "string" ? camera.detail : "Could not save the selected camera.");
        }
        cameraIsConfigured = true;
        setMessage(camera.message);
      } else if (cameraConfigured) {
        const cameraResponse = await fetch("/api/v1/stream/camera_source", { method: "DELETE" });
        const camera = await cameraResponse.json();
        if (!cameraResponse.ok) {
          throw new Error(typeof camera.detail === "string" ? camera.detail : "Could not clear the camera selection.");
        }
        cameraIsConfigured = false;
      }

      setCameraConfigured(cameraIsConfigured);
      onSaved(shift, cameraIsConfigured);
      onClose();
    } catch (saveError) {
      setError(saveError.message || "Could not save setup.");
    } finally {
      setLoading(false);
    }
  };

  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <section role="dialog" aria-modal="true" aria-labelledby="setup-title" className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-100 bg-white p-5 sm:p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-sky-700">Workspace setup</p>
            <h2 id="setup-title" className="mt-1 text-xl font-bold text-slate-900">Camera & shift settings</h2>
            <p className="mt-1 text-sm text-slate-500">Choose a camera yourself and set your team's working hours.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close setup" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            <i data-lucide="x" className="h-5 w-5"></i>
          </button>
        </header>

        <form onSubmit={save} className="space-y-6 p-5 sm:p-6">
          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold text-slate-900">Camera (optional)</legend>
            <p className="text-xs text-slate-500">No camera starts automatically. Select one now, or leave it unselected and set it up later.</p>
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-800">
              <option value="none">Don't select a camera yet</option>
              <option value="webcam">Laptop / USB webcam</option>
              <option value="rtsp">Network camera (RTSP)</option>
            </select>
            {sourceType === "webcam" && (
              <select value={webcamIndex} onChange={(event) => setWebcamIndex(event.target.value)} required className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-800">
                <option value="" disabled>Select a webcam</option>
                {[0, 1, 2, 3, 4].map((index) => <option key={index} value={String(index)}>Camera {index}{index === 0 ? " (often built-in)" : ""}</option>)}
              </select>
            )}
            {sourceType === "rtsp" && (
              <input value={rtspUrl} onChange={(event) => setRtspUrl(event.target.value)} required placeholder="rtsp://camera-address/stream" className="w-full rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-800" />
            )}
          </fieldset>

          <fieldset className="space-y-3 border-t border-slate-100 pt-5">
            <legend className="text-sm font-semibold text-slate-900">Shift schedule</legend>
            <label className="block text-xs font-medium text-slate-600">Schedule name
              <input value={form.name} onChange={(event) => set("name", event.target.value)} required maxLength="100" className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs font-medium text-slate-600">Starts
                <input type="time" value={form.start_time} onChange={(event) => set("start_time", event.target.value)} required className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
              <label className="text-xs font-medium text-slate-600">Ends
                <input type="time" value={form.end_time} onChange={(event) => set("end_time", event.target.value)} required className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs font-medium text-slate-600">Late grace (minutes)
                <input type="number" min="0" max="240" value={form.grace_minutes} onChange={(event) => set("grace_minutes", event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
              <label className="text-xs font-medium text-slate-600">Half-day after (hours)
                <input type="number" min="0.5" max="24" step="0.5" value={form.half_day_hours} onChange={(event) => set("half_day_hours", event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-600">Working days</p>
              <div className="mt-2 flex flex-wrap gap-2">{days.map((day, index) => (
                <button key={day} type="button" onClick={() => toggleDay(index)} className={`rounded-full border px-3 py-2 text-xs ${form.work_days.includes(index) ? "border-sky-300 bg-sky-50 text-sky-700" : "border-slate-200 text-slate-500"}`}>{day}</button>
              ))}</div>
            </div>
          </fieldset>

          {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
          {message && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
          <footer className="flex flex-col-reverse justify-end gap-2 border-t border-slate-100 pt-4 sm:flex-row">
            <button type="button" onClick={onClose} className="rounded-xl px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50">Close for now</button>
            <button disabled={loading} className="rounded-xl bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-60">{loading ? "Saving settings…" : "Save settings"}</button>
          </footer>
        </form>
      </section>
    </div>
  );
};
