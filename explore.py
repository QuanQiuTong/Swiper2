from phase1_explorer import Phase1Explorer
from phase2_swiper import Phase2Swiper

PACKAGE_ANDROID_WORLD = {
        # "Settings": "com.android.settings",               # 系统设置
        # "Calculator": "com.google.android.calculator",    # 计算器 (Pixel默认)
        # "Clock": "com.google.android.deskclock",          # 时钟
        # "Contacts": "com.google.android.contacts",        # 联系人
        # "Files": "com.google.android.documentsui",        # 文件管理器
        # "Chrome": "com.android.chrome",                   # 浏览器
        # "Calendar": "com.google.android.calendar",        # 日历
        # "Photos/Gallery": "com.google.android.apps.photos", # 相册
        # "Camera": "com.android.camera2",                  # 相机 (AOSP原生) 或 com.google.android.GoogleCamera
        # "Messages": "com.google.android.apps.messaging",  # 短信
        # "Phone": "com.google.android.dialer",             # 拨号/电话
        # "Maps": "com.google.android.apps.maps",           # 地图 (可选跳过登录)
        "YouTube": "com.google.android.youtube",          # YouTube (可选跳过登录)
    }

for name, pkg in PACKAGE_ANDROID_WORLD.items():
    print(f"\n=== 探索应用: {name} ({pkg}) ===")
    explorer = Phase1Explorer(package_name=pkg, max_depth=2)
    explorer.run_exploration()

for name, pkg in PACKAGE_ANDROID_WORLD.items():
    print(f"\n=== 合成滑动数据: {name} ({pkg}) ===")
    swiper = Phase2Swiper(package_name=pkg, use_local_vlm=False)
    swiper.run_synthesis()
