import json
import time
import shutil
from pathlib import Path
from core.device_controller import UIAutomatorController
from utils.image_utils import convert, calculate_image_diff


class Phase2Swiper:
    def __init__(self, package_name: str, use_local_vlm=True):
        self.package = package_name
        self.controller = UIAutomatorController()
        
        # 自由切换本地模型 or 远程服务
        if use_local_vlm:
            from core.local_vlm import LocalVLMClient
            # 直接指定你的本地模型路径
            self.vlm = LocalVLMClient(model_path=r"D:\Games\Qwen3-VL-4B-Instruct")
        else:
            from core.vlm_client import VLMClient
            self.vlm = VLMClient(server_url="http://127.0.0.1:8000")
        
        # Phase 1 骨架构建完成后的页面存档路径
        self.input_dir = Path("outputs") / self.package
        self.memory_file = self.input_dir / "memory_graph.json"
        
        # Phase 2 成功执行并验证的滑动数据集输出目录
        self.output_dir = Path("outputs") / f"{self.package}_dataset"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.successful_swipes =[]

    def load_memory(self):
        if not self.memory_file.exists():
            raise FileNotFoundError(f"找不到 Phase 1 的地图数据: {self.memory_file}")
        with open(self.memory_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_synthesis(self):
        print(f"=== 启动 Phase 2 滑动数据合成流水线 (App: {self.package}) ===")
        pages = self.load_memory()
        print(f"已加载 {len(pages)} 个独立页面进行评估。")

        for page in pages:
            page_id = page['page_id']
            img_path = page['image_path']
            trajectory = page['trajectory']
            
            print(f"\n--- 正在分析页面: {page_id} ---")
            
            # 1. 离线调用本地 VLM 获取可滑动区域
            regions = self.vlm.analyze_slidable_regions(img_path)
            if not regions:
                print(f"  -> VLM 认为此页面没有可滑动区域，跳过。")
                continue
                
            print(f"  -> VLM 检测到 {len(regions)} 个候选滑动区域。")

            # 2. 遍历每个候选区域，执行复现与验证
            for idx, region in enumerate(regions):
                print(f"[候选 {idx+1}/{len(regions)}] {region.get('type')} ({region.get('direction')})")
                
                # 步骤 A：回放路径，让手机回到这个页面
                print(f"    -> 正在重置 App 并沿着轨迹回放...")
                self.controller.replay_trajectory(self.package, trajectory)
                
                # 步骤 B：执行滑动前的截图
                before_img = str(self.output_dir / "temp_before.png")
                self.controller.take_screenshot(before_img)
                
                # 步骤 C：执行滑动
                swipe_params = self.controller.swipe_by_normalized_bbox(
                    bbox=region['bbox'],
                    direction=region['direction']
                )
                
                # 步骤 D：执行滑动后的截图
                after_img = str(self.output_dir / "temp_after.png")
                self.controller.take_screenshot(after_img)
                
                # 步骤 E：对比验证
                is_success = calculate_image_diff(before_img, after_img, threshold=0.01)
                
                if is_success:
                    print("    -> ✅ 验证成功！页面发生了实质性变化，保存为有效数据。")
                    dataset_id = f"{page_id}_swipe_{idx}"
                    final_before = self.output_dir / f"{dataset_id}_before.png"
                    final_after = self.output_dir / f"{dataset_id}_after.png"
                    
                    shutil.move(before_img, final_before)
                    shutil.move(after_img, final_after)
                    
                    # Old format for dataset entry, can be extended with more metadata if needed
                    {
                        "dataset_id": dataset_id,
                        "source_page": page_id,
                        "intent": region.get('description', ''),
                        "vlm_bbox": region['bbox'],
                        "swipe_params": swipe_params,
                        "before_image": str(final_before),
                        "after_image": str(final_after)
                    }

                    sx, sy = swipe_params['start']
                    ex, ey = swipe_params['end'] 

                    action = {
                        "action": "swipe",
                        "bbox": region['bbox'],
                        "instruction": region.get('description', ''),
                        "start": convert([sx, sy]),
                        "end": convert([ex, ey]),
                        "duration": swipe_params['duration'],
                        "direction": region.get('direction', '')
                    }
                       
                    if sx == ex:  # x不变，竖向滑动
                        action['direction'] = "up" if sy > ey else "down"
                    elif sy == ey:  # y不变，横向滑动
                        action['direction'] = "left" if sx > ex else "right"
                    else: # 并非纯水平或垂直滑动，暂不标记
                        pass

                    # 我们项目的数据结构
                    self.successful_swipes.append({
                        "img_filename": str(final_before),
                        "action_data": action
                    })
                    self.save_dataset()
                else:
                    print("    -> ❌ 验证失败！滑动后页面无变化（可能已经到底部了或 VLM 误判）。丢弃该数据。")

        print(f"\n=== Phase 2 完成！共合成 {len(self.successful_swipes)} 条有效的高质量滑动数据。 ===")

    def save_dataset(self):
        out_file = self.output_dir / "swipe_dataset.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(self.successful_swipes, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    target_app = "com.deepseek.chat"
    swiper = Phase2Swiper(package_name=target_app, use_local_vlm=False)
    swiper.run_synthesis()