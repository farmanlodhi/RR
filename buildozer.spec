[app]

title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

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
    openpyxl,\
    pyjnius

android.permissions = \
    CAMERA,\
    READ_EXTERNAL_STORAGE,\
    WRITE_EXTERNAL_STORAGE,\
    INTERNET,\
    ACCESS_NETWORK_STATE

android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21

# Pin build-tools to 33.0.2 — avoids the newer versions that hit licence issues
android.build_tools_version = 33.0.2

# Licences can be pulled in for packages resolved as dependencies during
# the actual install step (e.g. a build-tools version not yet known when
# buildozer first primes licences), which otherwise blocks the build with
# an unanswered "Accept? (y/N)" prompt. The CI workflow also pipes `yes`
# into buildozer as a second layer of defence for the same reason.
android.accept_sdk_license = True

# Pin python-for-android to this specific tagged release. Without this,
# buildozer clones p4a's current `master` branch, which now includes
# newer-architecture work (originally on the `develop` branch) that
# builds Kivy via a generic `pip install` inside a venv instead of p4a's
# dedicated Kivy recipe. The generic pip build doesn't set the
# Android/GLES cross-compile flags Kivy's setup.py needs, so it tries to
# compile against desktop OpenGL headers (GL/gl.h) that don't exist in
# the NDK sysroot, and fails with "'GL/gl.h' file not found". This tag
# still uses the old recipe-based build, which sets those flags correctly.
p4a.branch = v2024.01.21

android.archs = arm64-v8a

android.enable_androidx = True

# Google ML Kit on-device text recognition (free OCR, model bundled in APK)
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.0

orientation = portrait

#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

[buildozer]

log_level = 2
warn_on_root = 1
