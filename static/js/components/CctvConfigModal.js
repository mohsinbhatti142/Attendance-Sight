// static/js/components/CctvConfigModal.js
window.CctvConfigModal = function CctvConfigModal({ isOpen, onClose }) {
  const [sourceType, setSourceType] = React.useState("none");
  const [webcamIndex, setWebcamIndex] = React.useState("");
  const [rtspUrl, setRtspUrl] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [msg, setMsg] = React.useState("");

  React.useEffect(() => {
    if (!isOpen) return;
    let active = true;
    fetch("/api/v1/stream/camera_source").then(async (response) => {
      if (!response.ok) throw new Error("Could not load camera settings.");
      return response.json();
    }).then((camera) => {
      if (!active || !camera.source) return;
      const source = String(camera.source);
      if (/^\d+$/.test(source)) {
        setSourceType("webcam");
        setWebcamIndex(source);
      } else {
        setSourceType("rtsp");
        setRtspUrl(source);
      }
    }).catch((error) => { if (active) setMsg(error.message); });
    return () => { active = false; };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleApply = async () => {
    setLoading(true);
    setMsg(sourceType === "none" ? "Clearing camera selection…" : "Saving camera selection…");

    try {
      const selected = sourceType === "webcam" ? webcamIndex : rtspUrl.trim();
      const res = sourceType === "none"
        ? await fetch("/api/v1/stream/camera_source", { method: "DELETE" })
        : await fetch(`/api/v1/stream/set_camera_source?source=${encodeURIComponent(selected)}`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Camera switch failed");
      setMsg(data.message || "Camera source updated!");
      setTimeout(() => {
        onClose();
      }, 1000);
    } catch (e) {
      setMsg(e.message || "Failed to switch camera source.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
      <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-200">
              <i data-lucide="video" className="w-4 h-4"></i>
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">Camera settings</h3>
              <p className="text-xs text-slate-500">Select a camera manually; none starts automatically</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100">
            <i data-lucide="x" className="w-5 h-5"></i>
          </button>
        </div>

        {/* Form */}
        <div className="p-6 space-y-4">
          {msg && (
            <div className="p-3 rounded-xl bg-indigo-50 border border-indigo-200 text-xs text-indigo-700 font-mono">
              {msg}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-2">Select Camera Source Type</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSourceType("none")}
                className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-2 transition-all ${
                  sourceType === "none"
                    ? "bg-indigo-50 border-indigo-400 text-indigo-700 shadow-sm"
                    : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-white"
                }`}
              >
                <i data-lucide="video-off" className="w-4 h-4"></i>
                <span>No camera</span>
              </button>
              <button
                type="button"
                onClick={() => setSourceType("webcam")}
                className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-2 transition-all ${
                  sourceType === "webcam"
                    ? "bg-indigo-50 border-indigo-400 text-indigo-700 shadow-sm"
                    : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-white"
                }`}
              >
                <i data-lucide="camera" className="w-4 h-4"></i>
                <span>USB / Laptop Webcam</span>
              </button>

              <button
                type="button"
                onClick={() => setSourceType("rtsp")}
                className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-2 transition-all ${
                  sourceType === "rtsp"
                    ? "bg-indigo-50 border-indigo-400 text-indigo-700 shadow-sm"
                    : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-white"
                }`}
              >
                <i data-lucide="cctv" className="w-4 h-4"></i>
                <span>Network camera</span>
              </button>
            </div>
          </div>

          {sourceType === "webcam" ? (
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Webcam Device Index</label>
              <select
                value={webcamIndex}
                onChange={(e) => setWebcamIndex(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500 font-mono"
              >
                <option value="" disabled>Select a webcam</option>
                <option value="0">Camera 0</option>
                <option value="1">Camera 1</option>
                <option value="2">Camera 2</option>
                <option value="3">Camera 3</option>
                <option value="4">Camera 4</option>
              </select>
            </div>
          ) : sourceType === "rtsp" ? (
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Network camera address</label>
              <input
                type="text"
                value={rtspUrl}
                onChange={(e) => setRtspUrl(e.target.value)}
                placeholder="rtsp://admin:password@192.168.1.64:554/Streaming/Channels/101"
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:bg-white focus:border-indigo-500 font-mono text-[11px]"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Format: <code className="text-slate-600 font-medium">rtsp://user:pass@ip:port/channel</code>
              </p>
            </div>
          ) : null}

          {/* Quick Guidance Box */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-1">
            <span className="font-semibold text-slate-800">Different WiFi / Network Tips:</span>
            <p className="text-[11px]">
                Choose “No camera” to stop automatic camera startup.
            </p>
          </div>

          {/* Buttons */}
          <div className="pt-3 flex justify-end space-x-2 border-t border-slate-100">
            <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-800">
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={loading}
              className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm flex items-center space-x-2"
            >
              <span>{loading ? "Saving..." : sourceType === "none" ? "Save without camera" : "Save camera"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
