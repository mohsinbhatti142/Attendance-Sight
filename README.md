# Attendance-Sight

**Private, local-first employee attendance with face recognition.**

Attendance-Sight is a self-hostable desktop-style application for managing employee profiles, recording attendance from a local camera, and reviewing reports. The Python service and recognition pipeline run on your own computer; Windows builds show the interface in an embedded app window, while source runs use your browser.

> **Local-use project:** The default server listens on `127.0.0.1` and is not intended to be exposed to the internet. This repository does not include face photos, biometric templates, model weights, a database, or a compiled executable.

## Demo

Watch the [Attendance-Sight demo video](https://github.com/mohsinbhatti142/Attendance-Sight/releases/download/v1.3.4/demo.mp4) (53 MB).
The demo shows the app interface and setup flow. Do not share real employees' faces or personal information in public demos.

## Download

Download the Windows installer and standalone executable from the [latest GitHub release](https://github.com/mohsinbhatti142/Attendance-Sight/releases/latest):

- `Attendance-Sight-Setup-1.3.4.exe` — recommended; installs the desktop app and Start Menu shortcut.
- `Attendance-Sight-1.3.4.exe` — portable standalone executable; no installer required.

The Windows app downloads its face-recognition model pack the first time it runs. Internet access is needed for this download and for some interface resources. See [Install and use the Windows desktop app](#install-and-use-the-windows-desktop-app) for setup instructions.

## Features

- Admin sign-in and employee directory.
- First-admin registration with just an email address and password; the email is the sign-in username.
- Optional email verification and password recovery after Gmail delivery is configured in Account Settings.
- Optional per-install Gmail SMTP sender configuration; its App Password is encrypted locally and is never bundled.
- Persistent administrator session for up to five days; the password itself is never saved by the app.
- One-time first-administrator registration; sign-in is shown first, and registration closes after the first account is made.
- In-app administrator password changes and verified sign-in email updates.
- Local camera capture and live attendance dashboard.
- Optional first-run camera and shift setup wizard; it can be dismissed and reopened from the account menu.
- Face detection and embedding with InsightFace ONNX models.
- Similarity search over enrolled face embeddings with FAISS.
- Attendance events, daily records, monthly summaries, and configurable shift rules.
- SQLite storage by default.
- AI model initialization in the background so the portal can open while models load.
- Clear AI readiness and active CPU/GPU provider status.
- Windows desktop installer; Python source is also available for local modification.

## How it works

1. The local FastAPI service initializes the SQLite database and opens the portal at `http://127.0.0.1:8000`.
2. On the first run, InsightFace downloads its `buffalo_l` model pack into the local data directory. Internet access is required for this first download. The current interface also loads React, Tailwind CSS, icons, and fonts from public CDNs, so internet access is needed for the complete UI.
3. The service builds a FAISS index from previously enrolled face templates. The camera stays stopped until an administrator selects one.
4. The dashboard reports **AI LOADING**, **AI READY · CPU**, **AI READY · GPU**, or **AI UNAVAILABLE**. AI endpoints remain unavailable until the model and index are ready.
5. Inference tries the NVIDIA CUDA provider when available; if GPU model initialization fails, it retries with CPU. Otherwise, it starts directly on CPU. Model setup runs in the background so the portal remains usable while AI initializes.

On Windows, the desktop build includes ONNX Runtime's CUDA provider and its matching CUDA/cuDNN runtime DLLs. The AI status reports the provider actually activated by the face models. **AI READY · CPU** means GPU initialization was unavailable and the app fell back to CPU; check `/health` and `%LOCALAPPDATA%\AttendSight\logs\app.log` for the provider and any CUDA initialization failure.

Model weights are deliberately not committed or bundled. A fresh install needs a working internet connection for the model download and enough free disk space for the download and extracted weights.

## Requirements

### Running from source

- Windows 10/11, 64-bit.
- Python 3.10.
- [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Internet access for the first model download.
- A webcam or supported camera/RTSP source for live attendance.
- 8 GB RAM recommended; more is helpful for model loading.
- NVIDIA GPU is optional. CPU inference works, but is slower.
- NVIDIA CUDA-capable GPU and a current NVIDIA driver are required for CUDA acceleration; the app falls back to CPU if the CUDA provider cannot initialize.

### Installing the Windows desktop app

- Windows 10/11, 64-bit.
- Internet access on first launch to download the model pack.
- Microsoft Edge WebView2 Runtime.
- A camera for live kiosk operation.
- No separate Python or uv installation is required.

The installer creates Start Menu and optional desktop shortcuts. Attendance-Sight opens in its own desktop window and runs locally; it is not a cloud-hosted service.

## Run from source

Clone the repository and open PowerShell in its directory:

```powershell
uv sync --frozen
Copy-Item .env.example .env
```

Before the first run, edit `.env` and set a private `SECRET_KEY`. For example, generate a signing key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then start the portal:

```powershell
uv run python run_portal.py
```

The default browser opens automatically when the server is ready. If it does not, visit `http://127.0.0.1:8000`.

On a new install, sign-in appears first and **Register** is shown below it until the first administrator exists. Registration is simple: enter your email, create a password, confirm it, then choose **Create account**. **Your email is your username**, and you can sign in immediately. No Gmail setup or email code is needed to register. Only one administrator can register.

**Forgot password?** requires email delivery and a verified address. After signing in, open **Account settings**, verify your sign-in email and configure a Gmail sender if you want to enable emailed password recovery. Gmail setup is optional and is never part of registration. Its App Password is encrypted and saved on that computer only. To create one, enable 2-Step Verification for the sender Gmail account and create an App Password in Google Account security settings. A normal Gmail password will not work. The sender account can be separate from your sign-in email.

## Install and use the Windows desktop app

The Windows installer creates a Start Menu entry and can create a desktop shortcut. Attendance-Sight opens in its own app window rather than a browser tab. It runs its local service in the background while that window is open. The installed app does not include face-model weights; it downloads those on first launch.

1. Run `Attendance-Sight-Setup-1.3.4.exe` from a trusted release or build it yourself using the steps below. The per-user installer does not require administrator privileges.
2. Launch **Attendance-Sight** from the Start Menu or desktop shortcut. Windows may show a SmartScreen warning for an unsigned personal build; only run executables you trust.
3. On the first run, choose **Register** below sign-in.
4. Enter your email address and create a password of at least 10 characters. Your email address is your username, and you can sign in immediately.
5. The desktop window opens while the AI model pack downloads in the background. Keep the computer online until the dashboard changes from **AI LOADING** to **AI READY**.
6. The first-run **Camera & shift settings** popup lets you choose a webcam or RTSP camera and save shift hours. Close the popup to skip and finish setup later from the account menu. No camera is selected or started automatically.
7. To enable **Forgot password?**, sign in first, then verify your email and configure Gmail delivery in **Account settings**. After that, the reset code is sent to your verified sign-in email.
8. Close the Attendance-Sight window to stop the local service.

The sign-in screen remembers your email address on this device; it never saves your password.

The installed app stores mutable files in:

```text
%LOCALAPPDATA%\AttendSight\
```

The app keeps its existing `%LOCALAPPDATA%\AttendSight` data folder so updates preserve your current database and settings. It contains the private `.env` signing key, SQLite database, selected camera and shift settings, face photos, downloaded models, FAISS index, and logs. Administrator credentials are stored as password hashes in the database. Back up this folder securely if you want to preserve local data. Deleting it removes the app's local records, credentials, and downloaded model files.

The embedded browser profile is stored under `%LOCALAPPDATA%\AttendSight\webview\` so your sign-in session survives closing and reopening the app.

The log file is:

```text
%LOCALAPPDATA%\AttendSight\logs\app.log
```

## Build the Windows installer

Build on a Windows machine with Python 3.10, uv, and Inno Setup 6 installed. Close any running Attendance-Sight server first, then run:

```powershell
.\scripts\build_windows.ps1
.\scripts\build_installer.ps1
```

The first script creates a dedicated `.build-venv`, installs the runtime requirements and PyInstaller, and writes a Windows desktop executable. The first creates the standalone executable:

```text
dist\Attendance-Sight-1.3.4.exe
```

The second packages it into:

```text
dist\Attendance-Sight-Setup-1.3.4.exe
```

When updating an existing install, Setup closes any running Attendance-Sight instances before replacing the old executable and does not reopen those old instances after the update. The installer and app are unsigned personal builds; Windows SmartScreen or organization-managed application policies may warn or block them. Do not disable Windows protections to run an untrusted build. Attendance-Sight uses the installed Microsoft Edge WebView2 Runtime to display its desktop UI.

The installer does not include model weights, employee data, or `.env` secrets. On first launch, the model pack downloads separately under `%LOCALAPPDATA%\AttendSight\data\models`.

## Configure the camera

Attendance-Sight does not start or select a camera on its own. Use the first-run **Camera & shift settings** popup, the account menu, or **Camera settings** to choose a webcam index explicitly or enter an RTSP address. A USB webcam is the simplest setup. RTSP cameras must be reachable from the same computer. You can close the setup popup without choosing a camera; live attendance and enrollment video require selecting one later.

The kiosk's camera badge and AI badge are separate:

- **AI READY · CPU/GPU** means the recognition model and matcher have initialized.
- **CAMERA LIVE** means the camera you selected is returning frames.

The AI can be ready while the camera is offline; check camera permissions, the selected device, and whether another application is using the camera.

## Data, privacy, and security

- Face images, face embeddings, attendance records, and model weights stay on the local computer by default.
- The default bind address is loopback (`127.0.0.1`). Do not change it to a public-facing address or forward the port to the internet without a separate security review and deployment design.
- `.env`, databases, camera snapshots, model weights, face images, FAISS files, build output, and source ZIPs are excluded by `.gitignore`. Review `git status` before every commit; do not commit real biometric data, secrets, or private logs.
- Use a unique admin password and signing key. Keep backups encrypted and limit access to the Windows account that owns the data.
- The Gmail App Password is encrypted in the local app data folder using the app's private signing key. Do not share that folder or commit its contents.
- The UI currently loads some fonts and JavaScript/CSS tools from public CDNs, so internet access may also be needed to load the full desktop UI.

## Face model licensing

Attendance-Sight's source code and third-party packages have their own licenses. The upstream [InsightFace model-zoo notice](https://github.com/deepinsight/insightface/tree/master/model_zoo) restricts its supplied pretrained models to **non-commercial research purposes**. Check the current model license and ensure your use is permitted before downloading or using the weights. This repository does not redistribute those weights.

## Troubleshooting

### The dashboard says “AI UNAVAILABLE”

Check `http://127.0.0.1:8000/health` and the application log. The `ai`, `model`, `matcher`, and `model_provider` fields describe initialization. Verify first-run internet access, free disk space, the model download, and any dependency or Windows security-policy errors in the log.

### The dashboard says “AI READY · CPU”

Recognition is running, but CPU inference may be slower. This is expected for the portable build. The model provider reported by `/health` is the provider actually being used, not just the provider requested.

### The dashboard says “AI READY · GPU”

The ONNX sessions are using CUDA. Keep compatible NVIDIA drivers and CUDA runtime dependencies installed. If CUDA cannot be initialized, Attendance-Sight falls back to CPU when that provider is available.

### The camera is offline

Allow camera access in Windows privacy settings, close other camera apps, and check the selected camera index. An IP camera must be reachable from the local computer.

### Port 8000 is already in use

Close the other local server using port 8000, or set `APP_PORT` in `.env` before starting Attendance-Sight. The browser URL uses the configured port.

### Windows blocks the executable

Some Windows systems enforce App Control or organization-managed application policies that block unsigned executables. Do not disable those protections to run Attendance-Sight. Ask the device administrator to approve a trusted, appropriately signed build, or use the Python source version if your policy allows it.

### The desktop window does not open

Attendance-Sight requires Microsoft Edge WebView2 Runtime. Install the official Evergreen Runtime from Microsoft's WebView2 page, then restart Attendance-Sight. The local service log is `%LOCALAPPDATA%\AttendSight\logs\app.log`.

Older versions may leave removed `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` entries in `%LOCALAPPDATA%\AttendSight\.env`. Current versions ignore these obsolete settings, so you do not need to delete your local data or configuration.

### Initial model download fails

Keep the machine online and inspect `app.log` for the download error. Check network/proxy restrictions and available disk space, then restart Attendance-Sight. Do not download model weights from untrusted mirrors.

## Repository layout

```text
src/                         FastAPI app, API routes, database, and AI services
static/                      Local portal HTML, JavaScript, and Attendance-Sight SVG branding
scripts/build_windows.ps1    Windows desktop executable build
scripts/build_installer.ps1  Windows installer build
scripts/Attendance-Sight.iss Per-user Windows installer definition
scripts/create_windows_icon.py
packaging/build-constraints.txt
data/                        Local runtime data (ignored by Git)
run_portal.py                Source and packaged-app launcher
pyproject.toml               Project dependencies and settings
uv.lock                      Reproducible uv dependency lock
```

## Technology

- Python 3.10, FastAPI, Uvicorn, SQLAlchemy, SQLite, and a browser-based React interface.
- InsightFace and ONNX Runtime for local face analysis.
- FAISS for searching locally stored face embeddings.
- PyInstaller and Inno Setup 6 for building the Windows desktop installer.

## License and contributions

Attendance-Sight's original application code is licensed under the [MIT License](./LICENSE). This does not relicense third-party packages or InsightFace's pretrained model weights; check their separate license terms before use. In particular, the upstream model-zoo notice restricts its supplied pretrained models to non-commercial research purposes. Do not submit real employee identities, face images, embeddings, secrets, or production attendance data in issues, pull requests, or demo videos.
