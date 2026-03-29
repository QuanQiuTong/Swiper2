SAVE_AFTER = False

import json
from pathlib import Path
from utils.packages import PACKAGE_INSTALLED

out_dir = Path("./summary")
out_dir.mkdir(parents=True, exist_ok=True)

summary = []

for name, pkg in {"X": "com.twitter.android"}.items():
    print(f"\n=== 整理应用: {name} ({pkg}) ===")

    dataset_path = Path(f"./outputs/{pkg}_dataset/swipe_dataset.json")

    if not dataset_path.exists():
        print(f"  [错误] 找不到数据文件: {dataset_path}")
        continue

    with open(dataset_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"原始数据集中共有 {len(data)} 条滑动记录。")
    if len(data) <= 1:
        print("异常数据：滑动记录过少，跳过整理。")
        continue

    for record in data:
        src_before = Path(record['img_filename'])

        if not src_before.exists():
            print(f"  [警告] 图片不存在: {src_before}")
            continue

        # === 生成新文件名（变短）===
        before_name = src_before.name                           # "page_{id}_swipe_{sid}_before.png"
        base_name = before_name.replace("_before.png", ".png")  # "page_{id}_swipe_{sid}.png"
        new_before_name = f"{pkg}_{base_name}"                  # "{package}_page_{id}_swipe_{sid}.png"

        # === 复制 before 图 ===
        Path(out_dir / new_before_name).write_bytes(src_before.read_bytes())

        # === 推断 after 图 ===
        if SAVE_AFTER:
            src_after = Path(str(src_before).replace("_before.png", "_after.png"))
            if src_after.exists():
                new_after_name = f"{pkg}_{src_after.name}"
                Path(out_dir / new_after_name).write_bytes(src_after.read_bytes())
            else:
                print(f"  [警告] after 图不存在: {src_after}")

        # === 直接使用 action_data ===
        action = record['action_data']

        summary.append({
            "img_filename": new_before_name,
            "action_data": action
        })

        print(f"  ✔ 已处理: {new_before_name}")

# === 保存 summary ===
summary_path = out_dir / "summary.json"
with open(summary_path, 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(f"\n=== 汇总完成，共 {len(summary)} 条数据 ===")
print(f"输出路径: {summary_path}")