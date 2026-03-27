import json
from pathlib import Path

out_dir = Path("./outputs/summary")
out_dir.mkdir(parents=True, exist_ok=True)

PACKAGE_ANDROID_WORLD = {
        "Settings": "com.android.settings",               # 系统设置
        "Calculator": "com.google.android.calculator",    # 计算器 (Pixel默认)
        "Clock": "com.google.android.deskclock",          # 时钟
        "Contacts": "com.google.android.contacts",        # 联系人
        "Files": "com.google.android.documentsui",        # 文件管理器
        "Chrome": "com.android.chrome",                   # 浏览器
        "Calendar": "com.google.android.calendar",        # 日历
        "Photos/Gallery": "com.google.android.apps.photos", # 相册
        "Camera": "com.android.camera2",                  # 相机 (AOSP原生) 或 com.google.android.GoogleCamera
        "Messages": "com.google.android.apps.messaging",  # 短信
        "Phone": "com.google.android.dialer",             # 拨号/电话
        "Maps": "com.google.android.apps.maps",           # 地图 (可选跳过登录)
        "YouTube": "com.google.android.youtube",          # YouTube (可选跳过登录)
    }

summary = []

for name, pkg in PACKAGE_ANDROID_WORLD.items():
    print(f"\n=== 整理应用: {name} ({pkg}) ===")
    try: 
        with open(f"./outputs/{pkg}_dataset/swipe_dataset.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"  [错误] 找不到数据文件: ./outputs/{pkg}_dataset/swipe_dataset.json")
        continue

    print(f"原始数据集中共有 {len(data)} 条滑动记录。")
    if len(data) <= 1:
        print("异常数据：滑动记录过少，跳过整理。")
        continue
    
    for record in data:
        # 复制滑动前的图片到 summary 目录，并重命名
        img_filename = record['before_image'].split("\\")[-1]
        print(f"正在处理滑动记录，图片文件: {img_filename}")
        src_path = Path(record['before_image'])
        dst_path = out_dir / f"{pkg}_{img_filename}"
        if src_path.exists():
            dst_path.write_bytes(src_path.read_bytes())
            print(f"  已复制图片: {dst_path.name}")
        else:
            print(f"  [警告] 滑动前图片不存在: {src_path}")
            continue
        
        after_img = record['after_image']
        (out_dir / f"{pkg}_{after_img.split('\\')[-1]}").write_bytes(Path(after_img).read_bytes())

        p = record['swipe_params']
        sx,sy = p['start']
        ex,ey = p['end']
    
        # 约到小数点后1位，转换为0-1000的坐标
        s = [round(sx*1000/1080, 1), round(sy*1000/2400, 1)]
        e = [round(ex*1000/1080, 1), round(ey*1000/2400, 1)]

        action = {
            "action": "swipe",
            "bbox": record['vlm_bbox'],
            "instruction": record['intent'],
            "start": s,
            "end": e,
            "duration": p['duration']*1000,
        }

        if sx == ex:  # x不变，竖向滑动
            action['direction'] = "up" if sy > ey else "down"
        elif sy == ey:  # y不变，横向滑动
            action['direction'] = "left" if sx > ex else "right"
        else: # 并非纯水平或垂直滑动，暂不标记
            pass

        summary.append({
            "img_filename": dst_path.name,
            "action_data": action
        })

# 将整理后的数据写入 summary.json
with open(out_dir / "summary.json", 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
    
"""
[
  {
    "img_filename": "com.warpengine.viggle_001.png",
    "action_data": {
      "action": "swipe",
      "bbox": [
        0,
        0,
        1000,
        1000
      ],
      "instruction": "Swipe up on the home page to discover more content",
      "success": true,
      "start": [
        500,
        900
      ],
      "end": [
        500,
        100
      ],
      "duration": 300,
      "direction": "up"
  },
]"""