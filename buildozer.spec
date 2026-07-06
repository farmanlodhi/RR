[app]

title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

# NOTE: openai/anthropic SDKs removed (pydantic-core/Rust won't build for
# Android) — AI calls use plain requests. pillow removed too: PyPI ships no
# Android wheels for it and the app now reads image sizes in pure Python.
# IMPORTANT: keep this on ONE line — buildozer does not support backslash
# line continuations and passes them literally into package names.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,plyer,requests,certifi,charset-normalizer,idna,urllib3,reportlab,openpyxl

android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,INTERNET,ACCESS_NETWORK_STATE

android.accept_sdk_license = True

android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21

# Pin build-tools to 33.0.2 — avoids the newer versions that hit licence issues
android.build_tools_version = 33.0.2

android.archs = arm64-v8a

android.enable_androidx = True

orientation = portrait

#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

[buildozer]

log_level = 2
warn_on_root = 1
