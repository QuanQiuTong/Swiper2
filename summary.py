import os
import json
import shutil
from pathlib import Path

def process_and_copy_item(item: dict, src_dir: Path, dest_dir: Path, pkg_name: str, existing_keys: set) -> bool:
    """处理单条记录：重命名防止冲突，判断是否已存在，增量拷贝文件"""
    before_name = item.get('img_filename')
    after_name = item.get('after_image')
    
    # 丢弃缺少图像引用的脏数据
    if not before_name or not after_name:
        return False
        
    # 构建加了包名前缀的新文件名
    new_before = f"{pkg_name}_{before_name}"
    new_after = f"{pkg_name}_{after_name}"
    
    # 【增量核心】如果这行数据已经在 summary 中存在，直接跳过，不再重复拷贝
    if new_before in existing_keys:
        return False
        
    src_before = src_dir / before_name
    src_after = src_dir / after_name
    
    # 丢弃物理文件丢失的脏数据
    if not src_before.exists() or not src_after.exists():
        return False
    
    # 拷贝图片资源
    shutil.copy(src_before, dest_dir / new_before)
    shutil.copy(src_after, dest_dir / new_after)
    
    # 顺带拷贝对应的 XML（如果有）
    xml_before = src_before.with_suffix('.xml')
    if xml_before.exists():
        shutil.copy(xml_before, dest_dir / new_before.replace('.png', '.xml'))
        
    xml_after = src_after.with_suffix('.xml')
    if xml_after.exists():
        shutil.copy(xml_after, dest_dir / new_after.replace('.png', '.xml'))
        
    # 更新 JSON 对象，指向新的文件名
    item['img_filename'] = new_before
    item['after_image'] = new_after
    item['package'] = pkg_name  # 显式写入 package 字段，方便后续精准统计
    
    return True

def summary(target_pkg=None):
    mode_text = f"for '{target_pkg}'" if target_pkg else "for ALL packages"
    print(f"\n=== 🚀 Starting Incremental Dataset Aggregation {mode_text} ===")
    
    outputs_dir = Path("outputs")
    summary_dir = Path("summary")
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    swipe_all_file = summary_dir / "swipe_all.json"
    click_all_file = summary_dir / "click_all.json"

    all_swipes_aggregated =[]
    all_clicks_aggregated =[]
    
    # 1. 预加载当前已存在的数据 (实现增量更新的基础)
    if swipe_all_file.exists():
        with open(swipe_all_file, 'r', encoding='utf-8') as f:
            all_swipes_aggregated = json.load(f)
            
    if click_all_file.exists():
        with open(click_all_file, 'r', encoding='utf-8') as f:
            all_clicks_aggregated = json.load(f)

    # 用 O(1) 的 Set 来缓存已存在的文件名
    existing_swipes = {item['img_filename'] for item in all_swipes_aggregated}
    existing_clicks = {item['img_filename'] for item in all_clicks_aggregated}

    app_stats = {}
    new_swipes_count = 0
    new_clicks_count = 0
    
    # 决定扫描的范围：如果指定了 target_pkg，就只扫那个包；否则扫描所有
    if target_pkg:
        dirs_to_process =[outputs_dir / f"{target_pkg}_dataset"]
    else:
        dirs_to_process = list(outputs_dir.glob("*_dataset"))
    
    for pkg_dir in dirs_to_process:
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            continue
            
        pkg_name = pkg_dir.name.replace("_dataset", "")
        print(f"  -> Scanning: {pkg_name}")
        app_stats[pkg_name] = {'click': 0, 'swipe': 0}
        
        # 2. 聚合 Swipe 数据
        swipe_file = pkg_dir / "swipe_dataset.json"
        if swipe_file.exists():
            with open(swipe_file, 'r', encoding='utf-8') as f:
                swipes = json.load(f)
            for item in swipes:
                if process_and_copy_item(item, pkg_dir, summary_dir, pkg_name, existing_swipes):
                    all_swipes_aggregated.append(item)
                    existing_swipes.add(item['img_filename'])
                    app_stats[pkg_name]['swipe'] += 1
                    new_swipes_count += 1

        # 3. 聚合 Click 数据
        click_file = pkg_dir / "click_dataset.json"
        if click_file.exists():
            with open(click_file, 'r', encoding='utf-8') as f:
                clicks = json.load(f)
            for item in clicks:
                if process_and_copy_item(item, pkg_dir, summary_dir, pkg_name, existing_clicks):
                    all_clicks_aggregated.append(item)
                    existing_clicks.add(item['img_filename'])
                    app_stats[pkg_name]['click'] += 1
                    new_clicks_count += 1

    # 如果有新数据产生，才去覆写 JSON，节省 I/O
    if new_swipes_count > 0 or new_clicks_count > 0:
        with open(swipe_all_file, 'w', encoding='utf-8') as f:
            json.dump(all_swipes_aggregated, f, ensure_ascii=False, indent=2)
            
        with open(click_all_file, 'w', encoding='utf-8') as f:
            json.dump(all_clicks_aggregated, f, ensure_ascii=False, indent=2)
            
        with open(summary_dir / "summary_all.json", 'w', encoding='utf-8') as f:
            json.dump(all_swipes_aggregated + all_clicks_aggregated, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Incremental aggregation complete!")
    print(f"📊 Newly added test cases in this run:")
    print(f"   -> Swipe Actions: +{new_swipes_count}")
    print(f"   -> Click Actions: +{new_clicks_count}")

    # ==========================
    # 🌟 1. 打印本次新增的数据分布 (仅在有新增时显示)
    # ==========================
    if new_swipes_count > 0 or new_clicks_count > 0:
        md_output = "\n### 📈 Newly Added Dataset Distribution\n\n"
        md_output += "| App Package | Click | Swipe | Total |\n"
        md_output += "| :--- | :---: | :---: | :---: |\n"
        total_c, total_s = 0, 0
        
        for app_name, counts in sorted(app_stats.items()):
            c, s = counts['click'], counts['swipe']
            t = c + s
            if t > 0:
                total_c += c; total_s += s
                md_output += f"| `{app_name}` | {c} | {s} | **{t}** |\n"

        md_output += f"| **New Added Total** | **{total_c}** | **{total_s}** | **{total_c + total_s}** |\n"
        print(md_output)

    # ==========================
    # 🌟 2. 打印全局(Overall)的数据分布
    # ==========================
    overall_stats = {}
    
    def extract_pkg(item):
        """兼容老数据的包名提取逻辑"""
        if 'package' in item:
            return item['package']
        name = item.get('img_filename', '')
        # 如果是老格式，从文件名推导包名
        return name.split('_page_')[0] if '_page_' in name else name.split('_')[0]

    # 统计汇总表
    for item in all_swipes_aggregated:
        pkg = extract_pkg(item)
        overall_stats.setdefault(pkg, {'click': 0, 'swipe': 0})['swipe'] += 1

    for item in all_clicks_aggregated:
        pkg = extract_pkg(item)
        overall_stats.setdefault(pkg, {'click': 0, 'swipe': 0})['click'] += 1

    md_overall = "\n### 📊 Overall Dataset Distribution\n\n"
    md_overall += "| App Package | Click | Swipe | Total |\n"
    md_overall += "| :--- | :---: | :---: | :---: |\n"
    grand_c, grand_s = 0, 0
    
    for app_name, counts in sorted(overall_stats.items()):
        c, s = counts['click'], counts['swipe']
        t = c + s
        grand_c += c
        grand_s += s
        md_overall += f"| `{app_name}` | {c} | {s} | **{t}** |\n"

    md_overall += f"| **Grand Total** | **{grand_c}** | **{grand_s}** | **{grand_c + grand_s}** |\n"
    print(md_overall)

if __name__ == "__main__":
    # 如果直接作为主程序运行，默认扫描所有包执行增量更新
    summary()