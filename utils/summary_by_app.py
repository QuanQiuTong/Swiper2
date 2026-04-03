import os
import json
import shutil
from pathlib import Path

def copy_resource(src_path: str, dest_dir: Path):
    """安全拷贝文件到目标目录"""
    if src_path and os.path.exists(src_path):
        shutil.copy(src_path, dest_dir)

def process_swipe_data(package_name: str, output_dir: Path) -> list:
    """提取并处理 Swipe 数据及关联文件"""
    dataset_file = Path(f"outputs/{package_name}_dataset/swipe_dataset.json")
    if not dataset_file.exists():
        return[]

    with open(dataset_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    processed_data =[]
    for item in raw_data:
        # 推导所有相关资源文件的路径
        before_img = item['img_filename']
        before_xml = before_img.replace('.png', '.xml')
        after_img = before_img.replace('_before.png', '_after.png')
        after_xml = after_img.replace('.png', '.xml')

        # 拷贝资源到 Summary 文件夹
        copy_resource(before_img, output_dir)
        copy_resource(before_img.replace('.png', '_skeleton.png'), output_dir) # 附带骨架图(若有)
        copy_resource(before_xml, output_dir)
        copy_resource(after_img, output_dir)
        copy_resource(after_xml, output_dir)

        # 净化 JSON：去除冗长的绝对路径，仅保留文件名
        clean_item = item.copy()
        clean_item['img_filename'] = os.path.basename(before_img)
        clean_item['after_image'] = os.path.basename(after_img) # 显式补齐 after_image，方便人工比对
        
        processed_data.append(clean_item)

    return processed_data

def process_click_data(package_name: str, output_dir: Path) -> list:
    """提取并处理 Click 数据及关联文件"""
    dataset_file = Path(f"outputs/{package_name}_dataset/click_dataset.json")
    if not dataset_file.exists():
        return[]

    with open(dataset_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    processed_data = []
    for item in raw_data:
        # 推导所有相关资源文件的路径
        before_img = item['img_filename']
        before_xml = before_img.replace('.png', '.xml')
        after_img = item['after_image']
        after_xml = after_img.replace('.png', '.xml')

        # 拷贝资源到 Summary 文件夹
        copy_resource(before_img, output_dir)
        copy_resource(before_xml, output_dir)
        copy_resource(after_img, output_dir)
        copy_resource(after_xml, output_dir)

        # 净化 JSON
        clean_item = item.copy()
        clean_item['img_filename'] = os.path.basename(before_img)
        clean_item['after_image'] = os.path.basename(after_img)
        
        processed_data.append(clean_item)

    return processed_data

def summarize_app(package_name: str):
    """为指定 App 生成最终的精华合集"""
    print(f"\n=== 开始生成测试集归档: {package_name} ===")
    
    # 创建目标目录
    output_dir = Path(f"summary/{package_name}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 处理数据
    swipes = process_swipe_data(package_name, output_dir)
    clicks = process_click_data(package_name, output_dir)

    # 1. 纯滑动数据
    with open(output_dir / "summary_swipe.json", 'w', encoding='utf-8') as f:
        json.dump(swipes, f, ensure_ascii=False, indent=2)

    # 2. 纯点击数据
    with open(output_dir / "summary_click.json", 'w', encoding='utf-8') as f:
        json.dump(clicks, f, ensure_ascii=False, indent=2)

    # 3. 混合完整数据
    with open(output_dir / "summary_swipe_and_click.json", 'w', encoding='utf-8') as f:
        json.dump(swipes + clicks, f, ensure_ascii=False, indent=2)

    print(f"✅ 打包完成！")
    print(f"  -> 滑动数据: {len(swipes)} 条")
    print(f"  -> 点击数据: {len(clicks)} 条")
    print(f"📁 归档位置: {output_dir.absolute()}")

if __name__ == "__main__":
    # 你可以把想打包的 App 列表写在这里批量运行
    apps_to_summarize =[
        "com.finch.finch",
        "xyz.blueskyweb.app",
        "company.thebrowser.arc",
        "com.bd.nproject",
        "ai.perplexity.comet",
        "ai.character.app",
        "com.wisernow.android"
    ]
    
    for app in apps_to_summarize:
        summarize_app(app)