[app]

title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

# Only packages that have a python-for-android recipe or are pure-Python
# with no compiled C extensions.
#
# REMOVED (no p4a recipe, C extensions fail cross-compilation):
#   openai, reportlab, openpyxl
#
# reportlab and openpyxl are imported inside try/except in the app so
# their absence won't crash anything — export buttons will just show
# an "install required" message on devices that lack them.
#
# kivy and kivymd are left unpinned so p4a picks its own known-good versions.
requirements = python3,\
    kivy,\
    kivymd,\
    plyer,\
    pillow,\
    requests,\
    certifi,\
    urllib3

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

android.build_tools_version = 33.0.2

android.archs = arm64-v8a

android.enable_androidx = True

orientation = portrait

#presplash.filename = %(source.dir)s/presplash.png
#icon.filename = %(source.dir)s/icon.png

[buildozer]

log_level = 2
warn_on_root = 1
