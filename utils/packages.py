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

PACKAGE_NEW = {
    # --- 2025 爆火的 AI 与效率工具 (全新 UI 形态) ---
    "DeepSeek": "com.deepseek.chat",               # 2025年登顶，全新思考链交互UI
    "Perplexity": "ai.perplexity.app.android",     # 搜索与对话结合的复杂交互
    "Arc Search": "company.thebrowser.arc",        # 极具创新的浏览器UI，非传统导航
    "Gemini": "com.google.android.apps.bard",      # 2025年大幅重构的 Google AI 界面
    
    # --- 新兴社交与通讯 (去中心化/新势力) ---
    "Bluesky": "xyz.blueskyweb.app",               # 2025年初用户暴增，全新改版
    "Threads": "com.instagram.barcelona",          # 纯文本流，极简风格的极致代表
    "Jagat": "io.jagat.lite",                      # 结合地图与社交的新兴 App
    
    # --- 创新交互与小众高分应用 (2025 Google Play 年度榜单常客) ---
    "Focus Friend": "com.underthing.focus.friend", # 游戏化 UI，打破常规布局
    "Wiser": "com.wisernow.android",               # 卡片化视听结合 UI
    "Finch": "com.finch.finch",                    # 宠物养成式习惯打卡，大量非标准组件
    "Perch Reader": "com.gmlabs.perch",            # 新型阅读器
}

PACKAGE_HOT_GLOBAL = {
    # --- 终极信息流测试 (高度依赖滑动) ---
    "TikTok": "com.zhiliaoapp.musically",          # 沉浸式全屏滑动、极少可见按钮
    "Instagram": "com.instagram.android",          # 横向滑动的 Stories，纵向滑动的 Feed
    "Twitter/X": "com.twitter.android",            # 密集的图文穿插、侧边抽屉菜单
    "Reddit": "com.reddit.frontpage",              # 复杂的帖子折叠、多层级评论区
    
    # --- 强业务逻辑测试 ---
    "Spotify": "com.spotify.music",                # 底部悬浮播放器、复杂动态列表
    "Amazon": "com.amazon.mShop.android.shopping", # 变态级密度的电商卡片与筛选逻辑
    "Discord": "com.discord",                      # 极度复杂的多层级侧边栏导航
}

PACKAGE_HOT_CN = {
    # --- 国民级应用 ---
    "WeChat": "com.tencent.mm",                    # 微信 (包含复杂的列表和底部导航)
    "Bilibili": "tv.danmaku.bili",                 # B站 (极其密集的视频封面网格、弹幕UI)
    "Meituan": "com.sankuai.meituan",              # 美团 (首页堪称功能入口大满贯，测试SoM极限)
    "Taobao": "com.taobao.taobao",                 # 淘宝 (瀑布流与复杂卡片的终极考验)
    "NetEase Music": "com.netease.cloudmusic",     # 网易云音乐 (转盘UI，复杂的播放页)
}

PACKAGE_INSTALLED = {
    # "DeepSeek": "com.deepseek.chat",      # √
    # "Wiser": "com.wisernow.android",      # 没多少页面，还充满了广告，不推荐。
    # "Perplexity": "ai.perplexity.app.android",
    # "ChatGPT": "com.openai.chatgpt",      # 假设的官方 ChatGPT App 包名
    # "Grok": "ai.x.grok",                  # 假设的 Grok App 包名

    # "Reddit": "com.reddit.frontpage",     # √
    "X/Twitter": "com.twitter.android",     # ing
    # "Threads": "com.instagram.barcelona", # 需要 Instagram 账号登录，暂不适合自动化测试
    "Spotify": "com.spotify.music",

}