# Receipt Reader — Android Build Guide

## What's in this package

| File | Purpose |
|---|---|
| `main.py` | The app |
| `buildozer.spec` | Buildozer build configuration |
| `.github/workflows/build.yml` | GitHub Actions — builds the APK in the cloud for free |
| `.gitignore` | Keeps secrets and build artefacts out of git |

---

## Quickest path: GitHub Actions (recommended)

No local setup needed. GitHub's servers build the APK for you.

### Step 1 — Create a GitHub repository

1. Go to [github.com](https://github.com) and sign in (free account is fine).
2. Click **New repository**.
3. Name it `receipt-reader` (or anything you like).
4. Leave it **Private** if you want (recommended — your API key is not in the repo, but still).
5. Click **Create repository**.

### Step 2 — Upload these files

Option A — via the GitHub website (no git needed):

1. On your new repo page click **Add file → Upload files**.
2. Drag all files from this zip into the upload area:
   - `main.py`
   - `buildozer.spec`
   - `.gitignore`
   - The folder `.github/workflows/build.yml` ← upload this keeping the folder path
3. Click **Commit changes**.

Option B — via git on your computer:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/receipt-reader.git
git push -u origin main
```

### Step 3 — Watch the build

1. In your repo click the **Actions** tab.
2. You'll see a workflow called **Build Android APK** running.
3. The first run takes **25–40 minutes** (it downloads the Android SDK/NDK).
4. Subsequent runs are **5–10 minutes** thanks to caching.

### Step 4 — Download the APK

1. Once the workflow shows a green ✓, click on it.
2. Scroll down to **Artifacts**.
3. Click **receipt-reader-apk** to download a zip.
4. Unzip it — inside is `receiptreader-1.0.0-arm64-v8a_armeabi-v7a-debug.apk`

### Step 5 — Install on your phone

1. Copy the APK to your Android phone (USB, Google Drive, WhatsApp to yourself — anything).
2. On the phone, open **Settings → Security** (or Privacy) and enable **Install unknown apps** for your file manager or browser.
3. Tap the APK file and follow the prompts.
4. Open **Receipt Reader**, go to **Menu → AI Settings** and enter your API key.

---

## Alternative: build locally on your own PC/Mac/Linux

> Requires Linux or WSL2 on Windows. Mac is not supported by Buildozer.

### Prerequisites

```bash
# Ubuntu / Debian / WSL2
sudo apt update
sudo apt install -y git zip unzip python3-pip python3-dev \
    build-essential libssl-dev libffi-dev autoconf automake \
    libtool pkg-config zlib1g-dev libncurses5-dev cmake lld ccache \
    openjdk-17-jdk

pip install buildozer cython==0.29.37
```

### Build

```bash
# Put main.py and buildozer.spec in the same folder, then:
buildozer android debug
```

The APK will appear in the `bin/` folder.

First build downloads ~4 GB of Android SDK/NDK — make sure you have space and a good connection.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails with `SDK licence not accepted` | Run `buildozer android debug` once interactively so it can prompt you to accept licences |
| `aidl not found` | Make sure `openjdk-17-jdk` (not just jre) is installed |
| APK installs but crashes on launch | Check logcat: `adb logcat | grep python` |
| Camera button does nothing | Grant Camera permission in phone Settings → Apps → Receipt Reader → Permissions |
| AI returns nothing | Open Menu → AI Settings, check key and model, use **Test Connection** |

---

## Updating the app

Edit `main.py`, push the change to GitHub, and a new APK is built automatically.
To bump the version, change `version = 1.0.0` in `buildozer.spec`.
