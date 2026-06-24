[app]
title = Receipt Reader
package.name = receiptreader
package.domain = org.gsi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0
requirements = hostpython3,\
    python3,\
    kivy==2.3.0,\
    kivymd==1.2.0,\
    plyer,\
    pillow,\
    openai,\
    requests,\
    certifi,\
    charset-normalizer,\
    urllib3,\
    openpyxl
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
