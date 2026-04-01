SAVE_AFTER = False

import json
import time
from pathlib import Path

out_dir = Path("./summaryClick")
out_dir.mkdir(parents=True, exist_ok=True)


def summary(packages: dict):

    summary = []

    def summary_app(name, pkg):
        print(f"\n=== 整理应用: {name} ({pkg}) ===")

        dataset_path = Path(f"./click/{pkg}_dataset/click_dataset.json")

        if not dataset_path.exists():
            print(f"  [错误] 找不到数据文件: {dataset_path}")
            return

        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"原始数据集中共有 {len(data)} 条点击记录。")
        if len(data) <= 1:
            print("异常数据：点击记录过少，跳过整理。")
            return

        for record in data:
            src_before = Path(record['img_filename'])

            if not src_before.exists():
                print(f"  [警告] 图片不存在: {src_before}")
                return

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

    for name, pkg in packages.items():
        summary_app(name, pkg)

    # === 保存 summary ===
    summary_path = out_dir / "summary.json"

    # 如果已经有 summary 文件了，就先备份一下，再将其与新数据合并后覆盖原文件
    if summary_path.exists():
        backup_path = out_dir / f"summary_backup_{int(time.time())}.json"
        summary_path.rename(backup_path)
        print(f"  -> 发现已有 summary 文件，已备份为: {backup_path}")

        with open(backup_path, 'r', encoding='utf-8') as f:
            existing_summary: list = json.load(f)

        # 合并去重
        existing_filenames = set(item['img_filename'] for item in existing_summary)
        new_entries = [item for item in summary if item['img_filename'] not in existing_filenames]
        if new_entries:
            print(f"  -> 合并了 {len(new_entries)} 条新数据到 summary 中。")
            summary = existing_summary + new_entries

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n=== 汇总完成，共 {len(summary)} 条数据 ===")
    print(f"输出路径: {summary_path}")


if __name__ == "__main__":
    from utils.packages import PACKAGE_INSTALLED

    GOOD_PACKAGES = {
    "DeepSeek": "com.deepseek.chat",      # √
    "Wiser": "com.wisernow.android",      # 没多少页面，还充满了广告，不推荐。
    "Perplexity": "ai.perplexity.app.android",
    
    "Grok": "ai.x.grok",                  # 假设的 Grok App 包名

    "Reddit": "com.reddit.frontpage",     # √
    "X/Twitter": "com.twitter.android",   # √
    "Spotify": "com.spotify.music",       # √

    "ChatGPT": "com.openai.chatgpt",
    "Perplexity": "ai.perplexity.app.android", # 新
    "Whatsapp": "com.whatsapp.w4b",
    "Manus": "tech.butterfly.app",  # Manus AI 办公助手，2025年新兴的效率工具，界面复杂且充满动态内容，非常适合测试 SoM 能力。
    "Gemini": "com.google.android.googlequicksearchbox", #
    "Youtube": "com.google.android.youtube",
    "Copilot": "com.microsoft.copilot"
}
    summary(GOOD_PACKAGES)
