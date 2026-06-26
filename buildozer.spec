[app]

title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

# Pure-Python packages only — no packages with unported C extensions.
# openai/anthropic SDKs are NOT listed here; the app calls the APIs
# directly via the 'requests' package instead (see InvoiceExtractor).
requirements = python3,\
    kivy==2.2.1,\
    kivymd==1.1.1,\
    plyer,\
    pillow,\
    requests,\
    certifi,\
    charset_normalizer,\
    urllib3,\
    openpyxl,\
    reportlab

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
