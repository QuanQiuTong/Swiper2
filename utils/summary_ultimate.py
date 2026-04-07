import os
import json
import shutil
from pathlib import Path

def clean_and_extract_valid_data(pkg_dir: Path, json_filename: str):
    """
    清理无效数据：如果 before 或 after 图片有任一丢失，则将该记录从 json 中剔除。
    不直接删除物理文件，以防多个动作共享同一张 before_image（如 Click 动作共享首页）。
    """
    dataset_file = pkg_dir / json_filename
    if not dataset_file.exists():
        return[]

    with open(dataset_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    valid_data =[]
    
    for item in raw_data:
        before_img = pkg_dir / item['img_filename']
        if 'after_image' not in item:
            print(f"  [Warning] Record missing 'after_image' field, temporarily kept: {item['img_filename']}")
            valid_data.append(item)  # 先保留，后续可以人工核实是否需要剔除
            continue
        after_img = pkg_dir / item['after_image']
        
        # 核心逻辑：只有两张图片都完好无损，才认为是有效数据
        if before_img.exists() and after_img.exists():
            valid_data.append(item)

    # 将清理后的纯净列表重新写回原包目录的 JSON
    with open(dataset_file, 'w', encoding='utf-8') as f:
        json.dump(valid_data, f, ensure_ascii=False, indent=2)

    return valid_data

def generate_ultimate_summary():
    print(f"\n=== 🚀 Starting Ultimate Dataset Cleaning and Aggregation ===")
    summary_base = Path("summary")
    
    # 准备并清空聚合输出目录
    all_dir = summary_base / "all"
    if all_dir.exists():
        shutil.rmtree(all_dir)
    all_dir.mkdir(parents=True, exist_ok=True)
    
    all_swipes_aggregated =[]
    all_clicks_aggregated =[]
    
    # 遍历 summary 下的所有包文件夹
    for pkg_name in os.listdir(summary_base):
        pkg_dir = summary_base / pkg_name
        
        # 忽略非文件夹和目标输出文件夹
        if not pkg_dir.is_dir() or pkg_name == "all":
            continue
            
        print(f"  -> Cleaning and aggregating: {pkg_name}")
        
        # 1. 清洗并获取有效数据
        valid_swipes = clean_and_extract_valid_data(pkg_dir, "summary_swipe.json")
        valid_clicks = clean_and_extract_valid_data(pkg_dir, "summary_click.json")
        
        # 顺手更新原包的 summary_swipe_and_click.json
        if valid_swipes or valid_clicks:
            with open(pkg_dir / "summary_swipe_and_click.json", 'w', encoding='utf-8') as f:
                json.dump(valid_swipes + valid_clicks, f, ensure_ascii=False, indent=2)

        # 2. 组装 Swipe 的最终测试集
        for item in valid_swipes:
            new_item = item.copy()
            orig_before_name = item['img_filename']
            
            # 防冲突：用包名作为前缀重命名文件
            new_img_name = f"{pkg_name}_{orig_before_name.replace("_before", "")}".replace("else_", "")  # 可选：如果包名有 else_ 前缀，可以在这里清理掉
            new_item['img_filename'] = new_img_name
            
            # 删除多余的 after_image 字段
            if 'after_image' in new_item:
                del new_item['after_image']
                
            # 仅拷贝 before 图片到 all 文件夹
            shutil.copy(pkg_dir / orig_before_name, all_dir / new_img_name)
            all_swipes_aggregated.append(new_item)

        # 3. 组装 Click 的最终测试集
        for item in valid_clicks:
            new_item = item.copy()
            orig_before_name = item['img_filename']
            
            new_img_name = f"{pkg_name}_{orig_before_name.replace("_before", "")}"
            new_item['img_filename'] = new_img_name
            
            if 'after_image' in new_item:
                del new_item['after_image']
                
            shutil.copy(pkg_dir / orig_before_name, all_dir / new_img_name)
            all_clicks_aggregated.append(new_item)

    # 4. 生成三个终极 JSON 文件
    with open(all_dir / "click_all.json", 'w', encoding='utf-8') as f:
        json.dump(all_clicks_aggregated, f, ensure_ascii=False, indent=2)
        
    with open(all_dir / "swipe_all.json", 'w', encoding='utf-8') as f:
        json.dump(all_swipes_aggregated, f, ensure_ascii=False, indent=2)
        
    with open(all_dir / "summary_all.json", 'w', encoding='utf-8') as f:
        json.dump(all_swipes_aggregated + all_clicks_aggregated, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Ultimate aggregation complete!")
    print(f"📊 Total high-quality gold-standard test cases obtained:")
    print(f"   -> Swipe Actions: {len(all_swipes_aggregated)}")
    print(f"   -> Click Actions: {len(all_clicks_aggregated)}")
    print(f"📁 Dataset securely packaged to: {all_dir.absolute()}")

    # ==========================
    # 🌟 统计每个包的有效数据量分布
    # ==========================
    app_stats = {}

    # 统计 Click
    for item in all_clicks_aggregated:
        app_name = item['img_filename'].split("_")[0]
        if app_name not in app_stats:
            app_stats[app_name] = {'click': 0, 'swipe': 0}
        app_stats[app_name]['click'] += 1

    # 统计 Swipe
    for item in all_swipes_aggregated:
        app_name = item['img_filename'].split("_")[0]
        if app_name not in app_stats:
            app_stats[app_name] = {'click': 0, 'swipe': 0}
        app_stats[app_name]['swipe'] += 1

    # 生成 Markdown 格式输出
    # md_output = "\n### 📈 Stat of App distribution in this dataset \n\n"
    md_output += "| App | Click | Swipe | Total |\n"
    md_output += "| :--- | :---: | :---: | :---: |\n"

    total_c = 0
    total_s = 0

    # 按包名按照字母顺序排序遍历
    for app_name, counts in sorted(app_stats.items()):
        c = counts['click']
        s = counts['swipe']
        t = c + s
        total_c += c
        total_s += s
        md_output += f"| `{app_name}` | {c} | {s} | **{t}** |\n"

    # 表格尾部统计总和
    md_output += f"| **All** | **{total_c}** | **{total_s}** | **{total_c + total_s}** |\n"

    print(md_output)

if __name__ == "__main__":
    generate_ultimate_summary()