[app]

title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.1

requirements = python3,\
    kivy==2.3.0,\
    kivymd==1.2.0,\
    camera4kivy,\
    gestures4kivy,\
    plyer,\
    pillow,\
    requests,\
    certifi,\
    charset-normalizer,\
    urllib3,\
    reportlab,\
    openpyxl

android.permissions = \
    CAMERA,\
    READ_EXTERNAL_STORAGE,\
    WRITE_EXTERNAL_STORAGE,\
    READ_MEDIA_IMAGES,\
    INTERNET,\
    ACCESS_NETWORK_STATE

# Target Android 15 (API 35) — removes the "built for an older version
# of Android" warning when installing. If the build fails on this,
# fall back to android.api = 34.
android.api = 35
android.minapi = 26
android.ndk = 25b
android.ndk_api = 26

android.archs = arm64-v8a

android.enable_androidx = True

# CameraX provider for camera4kivy — the camerax_provider folder must
# exist in the project root (cloned in the GitHub Actions workflow).
p4a.hook = camerax_provider/gradle_options.py

# Local recipes (reportlab 4.x override)
p4a.local_recipes = ./p4a-recipes

orientation = portrait

#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

[buildozer]

log_level = 2
warn_on_root = 1
