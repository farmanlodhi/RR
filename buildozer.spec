[app]

# App identity
title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

# Source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# Version
version = 1.0.0

# Requirements — keep this list lean; unused heavy packages cause build failures
requirements = python3,\
    kivy==2.3.0,\
    kivymd==1.2.0,\
    plyer,\
    pillow,\
    openai,\
    requests,\
    certifi,\
    charset-normalizer,\
    urllib3,\
    reportlab,\
    openpyxl

# Android permissions
android.permissions = \
    CAMERA,\
    READ_EXTERNAL_STORAGE,\
    WRITE_EXTERNAL_STORAGE,\
    INTERNET,\
    ACCESS_NETWORK_STATE

# Android SDK/NDK versions — pinned for reproducibility
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.ndk_api = 21

# Single arch for faster/more reliable CI builds.
# arm64-v8a covers all modern Android phones (2017+).
# Add armeabi-v7a later if you need to support very old devices.
android.archs = arm64-v8a

# AndroidX required by modern KivyMD
android.enable_androidx = True

# Orientation
orientation = portrait

# Presplash / icon — uncomment and add files to use custom branding
#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

# Do NOT set p4a.branch — let buildozer use its own pinned p4a version.
# Setting it to 'develop' pulls the latest unpinned commit which often breaks.
# p4a.branch = develop

[buildozer]

# Log level: 0=error, 1=info, 2=debug
log_level = 2

# Warn on root
warn_on_root = 1
