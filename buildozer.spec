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

# Requirements
# Note: openai and anthropic are pure-Python; reportlab/openpyxl are optional exports
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

# Android SDK / NDK — buildozer will download these automatically
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.ndk_api = 21

# Architecture — armeabi-v7a covers most Android phones;
# add arm64-v8a for 64-bit phones (makes APK larger but broader support)
android.archs = arm64-v8a, armeabi-v7a

# Enable AndroidX
android.enable_androidx = True

# Orientation
orientation = portrait

# Presplash / icon — replace these with your own files if available
#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

# Gradle / build
android.gradle_dependencies =

# Logcat filter during debug
android.logcat_filters = *:S python:D

# p4a branch
p4a.branch = develop

[buildozer]

# Log level: 0=error, 1=info, 2=debug
log_level = 2

# Warn on root
warn_on_root = 1
