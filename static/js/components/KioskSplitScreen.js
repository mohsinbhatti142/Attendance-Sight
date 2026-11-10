// static/js/components/KioskSplitScreen.js
window.KioskSplitScreen = function KioskSplitScreen({
  fps,
  totalEnrolled,
  todayPresent,
  lateArrivals,
  recentEvents,
  cameraActive,
  modelReady,
  aiStatus,
  modelProvider,
  shiftPolicy,
  onOpenEnrollModal,
  onOpenCctvModal,
}) {
  const [fullscreen, setFullscreen] = React.useState(false);
  const videoRef = React.useRef(null);

  const toggleFullscreen = () => {
    const el = document.getElementById("kiosk-container");
    if (!document.fullscreenElement) {
      if (el.requestFullscreen) el.requestFullscreen();
      setFullscreen(true);
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
      setFullscreen(false);
    }
  };

  return (
    <div id="kiosk-container" className="space-y-4">
      {/* Camera feed and attendance overview */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Camera and daily attendance summary */}
        <div className="lg:col-span-7 xl:col-span-7 flex flex-col space-y-4">
          {/* Live Viewport Card */}
          <div className="interactive-card bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
            {/* Viewport Top Controls Bar */}
            <div className="px-4 py-3 bg-white border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
              <div className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full border text-[11px] font-mono ${cameraActive ? "bg-emerald-50 border-emerald-200 text-emerald-700":"bg-amber-50 border-amber-200 text-amber-800"}`}>
                  <span className={`w-2 h-2 rounded-full ${cameraActive ? "bg-emerald-500 animate-ping":"bg-amber-500"}`}></span>
                  <span className="font-semibold">{cameraActive ? "CAMERA LIVE" : "CAMERA OFFLINE"}</span>
                </div>
                  <div className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full border text-[11px] font-mono ${
                    modelReady
                      ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                      : aiStatus === "loading" || aiStatus === "starting"
                        ? "bg-sky-50 border-sky-200 text-sky-700"
                        : "bg-rose-50 border-rose-200 text-rose-700"
                  }`}>
                    <span className={`w-2 h-2 rounded-full ${
                      modelReady ? "bg-emerald-500" : aiStatus === "loading" || aiStatus === "starting" ? "bg-sky-500 animate-pulse" : "bg-rose-500"
                    }`}></span>
                    <span className="font-semibold">
                      {modelReady
                        ? `AI READY · ${modelProvider === "CUDAExecutionProvider" ? "GPU" : modelProvider === "CPUExecutionProvider" ? "CPU" : modelProvider}`
                        : aiStatus === "loading" || aiStatus === "starting"
                          ? "AI LOADING"
                          : aiStatus === "demo"
                            ? "AI DEMO MODE"
                            : "AI UNAVAILABLE"}
                    </span>
                  </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={toggleFullscreen}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors border border-slate-200"
                  title="Toggle Fullscreen"
                >
                  <i data-lucide={fullscreen ? "minimize" : "maximize"} className="w-4 h-4"></i>
                </button>
              </div>
            </div>

            {/* Video Viewport */}
            <div className="relative w-full aspect-[16/10] max-h-[min(54vh,560px)] bg-slate-950 flex items-center justify-center">
              {modelReady ? (
                <img
                  ref={videoRef}
                  src="/api/v1/stream/video_feed"
                  alt="Live attendance camera feed"
                  className="w-full h-full object-cover select-none"
                  onError={(e) => {
                    e.target.style.display = "none";
                    const fallback = document.getElementById("video-fallback");
                    if (fallback) fallback.classList.replace("hidden", "flex");
                  }}
                />
              ) : null}
              {!modelReady && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 p-8 text-center bg-slate-950">
                  <i data-lucide="video-off" className="w-12 h-12 mb-3 text-slate-500"></i>
                  <p className="text-sm font-medium text-slate-200">
                    {aiStatus === "loading" || aiStatus === "starting"
                      ? "AI services are initializing…"
                      : aiStatus === "demo"
                        ? "AI processing is disabled in demo mode."
                        : "AI services are unavailable. Check the server logs."}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    {aiStatus === "loading" || aiStatus === "starting"
                      ? "The portal is available while models load."
                      : cameraActive ? "Camera connected" : "Camera is offline"}
                  </p>
                </div>
              )}
              {modelReady && (
                <div id="video-fallback" className="absolute inset-0 hidden flex-col items-center justify-center text-slate-400 p-8 text-center bg-slate-950">
                  <i data-lucide="video-off" className="w-12 h-12 mb-3 text-slate-500"></i>
                  <p className="text-sm font-medium text-slate-200">{cameraActive ? "Camera connected" : "Camera is offline"}</p>
                  <p className="text-xs text-slate-400 mt-1">Face recognition is ready.</p>
                </div>
              )}
            </div>

            {/* Viewport Bottom Info Strip */}
            <div className="px-4 py-2.5 bg-slate-50 border-t border-slate-200/80 flex items-center justify-between gap-3 text-xs font-mono text-slate-600">
              <span className="text-slate-500 font-sans">Pause in view until green <strong className="text-emerald-700">Checked in</strong> confirms your attendance.</span>
              <div className="flex items-center space-x-3">
                <span className="hidden sm:inline text-slate-500">Local kiosk</span>
                <button
                  onClick={onOpenCctvModal}
                  className="text-indigo-600 hover:text-indigo-700 font-sans font-medium underline text-xs"
                >
                  Camera settings
                </button>
              </div>
            </div>
          </div>

          {/* Quick Metrics Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="interactive-card bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Total Workforce</span>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-2xl font-bold text-slate-900 font-mono">{totalEnrolled}</span>
                <span className="text-xs text-slate-400">Profiles</span>
              </div>
            </div>

            <div className="interactive-card bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <span className="text-[11px] font-semibold text-emerald-700 uppercase tracking-wider">Present Today</span>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-2xl font-bold text-emerald-600 font-mono">{todayPresent}</span>
                <span className="text-xs text-emerald-600 font-medium font-mono">
                  {totalEnrolled > 0 ? `${Math.round((todayPresent / totalEnrolled) * 100)}%` : "0%"}
                </span>
              </div>
            </div>

            <div className="interactive-card bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <span className="text-[11px] font-semibold text-amber-700 uppercase tracking-wider">Late Arrivals</span>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-2xl font-bold text-amber-600 font-mono">{lateArrivals}</span>
                <span className="text-xs text-slate-400">Late after: {shiftPolicy ? (()=>{const [h,m]=shiftPolicy.start_time.split(":").map(Number);const t=new Date(2000,0,1,h,m+Number(shiftPolicy.grace_minutes));return t.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})})() : "—"}</span>
              </div>
            </div>

            <div className="interactive-card bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <span className="text-[11px] font-semibold text-indigo-700 uppercase tracking-wider">Shift schedule</span>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-base font-bold text-slate-800 font-mono">{shiftPolicy ? `${shiftPolicy.start_time}–${shiftPolicy.end_time}` : "—"}</span>
                <span className="text-[11px] text-slate-400">{shiftPolicy ? `${shiftPolicy.grace_minutes} min grace` : "Rules loading"}</span>
              </div>
            </div>
          </div>
        </div>

          {/* Recent attendance records */}
        <div className="lg:col-span-5 xl:col-span-5 flex flex-col space-y-4">
          <div className="interactive-card bg-white border border-slate-200 rounded-2xl p-4 flex flex-col h-[min(760px,calc(54vh+150px))] min-h-[390px] shadow-sm">
            {/* Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-100">
              <div className="flex items-center space-x-2.5">
                <div className={`w-2.5 h-2.5 rounded-full ${modelReady ? "bg-emerald-500 animate-pulse" : "bg-slate-300"}`}></div>
                <h3 className="text-sm font-bold text-slate-900 tracking-tight">Live Attendance Stream</h3>
              </div>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium border border-slate-200">
                {recentEvents.length} Recent Scans
              </span>
            </div>

            {/* Scrollable Feed */}
            <div className="flex-1 overflow-y-auto space-y-2.5 pt-3.5 pr-1 custom-scrollbar">
              {recentEvents.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
                  <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-3 text-slate-400">
                    <i data-lucide="user-check" className="w-6 h-6"></i>
                  </div>
                  <p className="text-sm font-semibold text-slate-700">Waiting for attendance events</p>
                  <p className="text-xs text-slate-400 mt-1 max-w-xs">
                    Recent attendance records will appear here when the kiosk service is connected.
                  </p>
                </div>
              ) : (
                recentEvents.map((evt, idx) => (
                  <div
                    key={`${evt.employee_id}-${idx}`}
                    className="p-3 rounded-xl bg-slate-50/80 border border-slate-200/90 hover:bg-white hover:border-indigo-300 hover:shadow-sm transition-all flex items-center justify-between"
                  >
                    {/* Left: Avatar & Info */}
                    <div className="flex items-center space-x-3 min-w-0">
                      <div className="relative">
                        {evt.snapshot ? (
                          <img
                            src={evt.snapshot}
                            alt={evt.name}
                            className="w-11 h-11 rounded-xl object-cover border border-slate-200 shadow-sm"
                            onError={(event) => { event.currentTarget.style.display = "none"; }}
                          />
                        ) : (
                          <div className="w-11 h-11 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-700 font-bold text-sm">
                            {evt.name ? evt.name.charAt(0).toUpperCase() : "E"}
                          </div>
                        )}
                        <span className="absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full bg-emerald-500 border-2 border-white flex items-center justify-center">
                          <i data-lucide="check" className="w-2 h-2 text-white"></i>
                        </span>
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm font-bold text-slate-900">{evt.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 font-mono font-medium">
                            {evt.code || `EMP-${evt.employee_id}`}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2 mt-0.5 text-xs text-slate-500">
                          <span className="text-indigo-600 font-mono font-medium">{evt.time}</span>
                          <span>•</span>
                          <span className="text-slate-400 text-[11px]">{evt.date}</span>
                        </div>
                      </div>
                    </div>

                    {/* Right: Badges */}
                      <div className="flex flex-col items-end space-y-1 shrink-0">
                      <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {evt.type || "CHECK_IN"}
                      </span>
                      <div className="flex items-center space-x-1.5 text-[11px] font-mono">
                        <span className="text-emerald-600 font-semibold">Match: {evt.confidence}%</span>
                        <span className="text-slate-300">|</span>
                        <span className="text-slate-500 text-[10px] font-bold">RECORDED</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Bottom Actions */}
            <div className="pt-3.5 border-t border-slate-100 flex items-center justify-between">
              <span className="text-xs text-slate-400 font-mono">Live attendance events</span>
              <button
                onClick={onOpenEnrollModal}
                className="px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all flex items-center space-x-1.5"
              >
                <i data-lucide="user-plus" className="w-3.5 h-3.5"></i>
                <span>Enroll New Face</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
