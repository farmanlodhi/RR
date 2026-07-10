[app]

title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

p4a.local_recipes = ./p4a-recipes

# NOTE: openai/anthropic SDKs removed (pydantic-core/Rust won't build for
# Android) — AI calls use plain requests. pillow removed too: PyPI ships no
# Android wheels for it and the app now reads image sizes in pure Python.
# liblzma added: CPython's _lzma module needs lzma built for the Android
# target ("fatal error: 'lzma.h' file not found"); the p4a recipe provides it.
# IMPORTANT: keep this on ONE line — buildozer does not support backslash
# line continuations and passes them literally into package names.
requirements = python3,liblzma,kivy==2.3.0,kivymd==1.2.0,plyer,requests,certifi,charset-normalizer,idna,urllib3,reportlab,openpyxl

android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,INTERNET,ACCESS_NETWORK_STATE

# ── Camera additions (build-safe, manifest-only) ─────────────────────
# Declare camera hardware features. required="false" is implied by
# buildozer's uses-feature output, so the app still installs on devices
# without a camera (file-picker fallback covers those).
android.features = android.hardware.camera,android.hardware.camera.autofocus
# Android 11+ package visibility: plyer's camera calls resolveActivity()
# on ACTION_IMAGE_CAPTURE, which returns null unless the intent is
# declared in a <queries> block. Without this, the camera button does
# nothing on API 30+ devices. The XML lives in extra_manifest.xml.
android.extra_manifest_xml = ./extra_manifest.xml

android.accept_sdk_license = True

android.api = 33
# minapi/ndk_api 26 (Android 8.0+) is required: CPython 3.11.5 (built by
# the pinned p4a) unconditionally compiles the grp module, which uses
# getgrent/setgrent — functions Android's libc only provides from API 26.
# At ndk_api 21 the build fails with "implicit declaration of setgrent".
android.minapi = 26
android.ndk = 25b
android.ndk_api = 26

# Pin build-tools to 33.0.2 — avoids the newer versions that hit licence issues
android.build_tools_version = 33.0.2

android.archs = arm64-v8a

android.enable_androidx = True

# ── Pin python-for-android to the last stable recipe-based release ──
# (v2024.01.21). Newer p4a (2026.x) switched to a Python 3.14 wheel-based
# build that requires Android wheels on PyPI, which core packages like
# pyjnius and pillow do not publish — causing "No matching distribution
# found" failures. The pinned release compiles everything from source
# using its own recipes and is the proven combo with NDK 25b + Kivy 2.3.0.
p4a.branch = master
p4a.commit = 957a3e5f8c270f7aa648ba185e5a68c1077a798d

orientation = portrait

#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

[buildozer]

log_level = 2
warn_on_root = 1
