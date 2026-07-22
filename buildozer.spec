[app]
title = 安全守护
package.name = elderlysafe
package.domain = com.elderlysafe.app
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0
requirements = python3,kivy>=2.0.0,plyer>=2.0.0,pyjnius>=1.4.0
orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.0.0
fullscreen = 1

# 安卓权限
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,ACCESS_BACKGROUND_LOCATION,SEND_SMS,CALL_PHONE,READ_PHONE_STATE,FOREGROUND_SERVICE,POST_NOTIFICATIONS,VIBRATE,RECEIVE_BOOT_COMPLETED,WAKE_LOCK

# 最低 API 级别 (Android 7.0+)
android.minapi = 24
android.targetapi = 33
android.api = 33

p4a.branch = master

# 架构 (armeabi-v7a 兼容大多数旧手机, arm64-v8a 兼容新手机)
android.arch = armeabi-v7a, arm64-v8a

# 允许大屏/老年机
android.allow_backup = True

# 日志级别
android.logcat_filters = *:S

[buildozer]
log_level = 2
warn_on_root = 1
