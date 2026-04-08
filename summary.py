import os
import json
import shutil
from pathlib import Path

def process_and_copy_item(item: dict, src_dir: Path, dest_dir: Path, pkg_name: str) -> bool:
    """处理单条记录：重命名防止冲突，并拷贝完好的配对文件"""
    before_name = item.get('img_filename')
    after_name = item.get('after_image')
    
    # 丢弃缺少图像引用的脏数据
    if not before_name or not after_name:
        return False
        
    src_before = src_dir / before_name
    src_after = src_dir / after_name
    
    # 丢弃物理文件丢失的脏数据
    if not src_before.exists() or not src_after.exists():
        return False
        
    # 构建加了包名前缀的新文件名 (例如 com.twitter_page_1_swipe_0_before.png)
    new_before = f"{pkg_name}_{before_name}"
    new_after = f"{pkg_name}_{after_name}"
    
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
    return True

def generate_ultimate_summary():
    print("\n=== 🚀 Starting Ultimate Dataset Aggregation ===")
    
    outputs_dir = Path("outputs")
    summary_dir = Path("summary")
    
    # 重置汇总目录
    if summary_dir.exists():
        shutil.rmtree(summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    all_swipes_aggregated = []
    all_clicks_aggregated =[]
    app_stats = {}
    
    # 扫描 outputs 目录下的所有 xxx_dataset 文件夹
    for pkg_dir in outputs_dir.glob("*_dataset"):
        if not pkg_dir.is_dir():
            continue
            
        pkg_name = pkg_dir.name.replace("_dataset", "")
        print(f"  -> Cleaning and aggregating: {pkg_name}")
        app_stats[pkg_name] = {'click': 0, 'swipe': 0}
        
        # 1. 聚合 Swipe 数据
        swipe_file = pkg_dir / "swipe_dataset.json"
        if swipe_file.exists():
            with open(swipe_file, 'r', encoding='utf-8') as f:
                swipes = json.load(f)
            for item in swipes:
                if process_and_copy_item(item, pkg_dir, summary_dir, pkg_name):
                    all_swipes_aggregated.append(item)
                    app_stats[pkg_name]['swipe'] += 1

        # 2. 聚合 Click 数据
        click_file = pkg_dir / "click_dataset.json"
        if click_file.exists():
            with open(click_file, 'r', encoding='utf-8') as f:
                clicks = json.load(f)
            for item in clicks:
                if process_and_copy_item(item, pkg_dir, summary_dir, pkg_name):
                    all_clicks_aggregated.append(item)
                    app_stats[pkg_name]['click'] += 1

    # 3. 生成三个终极 JSON 索引文件
    with open(summary_dir / "swipe_all.json", 'w', encoding='utf-8') as f:
        json.dump(all_swipes_aggregated, f, ensure_ascii=False, indent=2)
        
    with open(summary_dir / "click_all.json", 'w', encoding='utf-8') as f:
        json.dump(all_clicks_aggregated, f, ensure_ascii=False, indent=2)
        
    with open(summary_dir / "summary_all.json", 'w', encoding='utf-8') as f:
        json.dump(all_swipes_aggregated + all_clicks_aggregated, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Ultimate aggregation complete!")
    print(f"📊 Total high-quality valid test cases obtained:")
    print(f"   -> Swipe Actions: {len(all_swipes_aggregated)}")
    print(f"   -> Click Actions: {len(all_clicks_aggregated)}")
    print(f"📁 Dataset securely packaged to: {summary_dir.absolute()}")

    # ==========================
    # 🌟 统计每个包的数据量分布
    # ==========================
    md_output = "\n### 📈 Dataset Distribution\n\n"
    md_output += "| App Package | Click | Swipe | Total |\n"
    md_output += "| :--- | :---: | :---: | :---: |\n"

    total_c = 0
    total_s = 0

    # 按字母顺序排序
    for app_name, counts in sorted(app_stats.items()):
        c = counts['click']
        s = counts['swipe']
        t = c + s
        # 忽略掉收集失败 (0 数据) 的空包
        if t > 0:
            total_c += c
            total_s += s
            md_output += f"| `{app_name}` | {c} | {s} | **{t}** |\n"

    md_output += f"| **Grand Total** | **{total_c}** | **{total_s}** | **{total_c + total_s}** |\n"
    
    print(md_output)

if __name__ == "__main__":
    generate_ultimate_summary()