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
        
        if use_local_vlm:
            from core.local_vlm import LocalVLMClient
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
        
        self.temp_dir = Path("outputs") / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
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
            
            print(f"\n==================================================")
            print(f"--- 正在处理节点: {page_id} ---")
            
            # 先通过轨迹到达目标页面 (关闭强校验，适应动态内容)
            print(f"  -> 正在沿着轨迹前往目标页面...")
            if not self.controller.replay_trajectory_unverified(self.package, trajectory):
                print(f"  -> ❌ 回放时跳出了目标 App ，跳过此页面。")
                continue
                
            # 当场截取当前实时画面
            live_img_path = str(self.temp_dir / f"live_{page_id}.png")
            self.controller.take_screenshot(live_img_path)
            
            all_swipe_candidates =[]
            
            # --- 来源 1：提取 Phase 1 中 XML 找到的组件 ---
            # 当场提取 XML 可滑动组件
            print(f"  -> 正在当场提取实时 XML 组件...")
            xml_components = self.controller.get_scrollable_elements_xml()
            
            if xml_components:
                print(f"  -> 发现 {len(xml_components)} 个 XML 可滑动组件，请求意图指令...")
                for comp in xml_components:
                    intent_cmd = self.vlm.generate_intent_for_xml_component(
                        live_img_path, comp['bounds'], comp['direction'], comp['text']
                    )
                    
                    # 坐标转换：把 XML 的物理坐标转成归一化坐标送进待测队列
                    w, h = self.controller.window_size
                    norm_bbox = [
                        int(comp['bounds'][0]/w*1000), int(comp['bounds'][1]/h*1000),
                        int(comp['bounds'][2]/w*1000), int(comp['bounds'][3]/h*1000)
                    ]
                    
                    all_swipe_candidates.append({
                        "category": "component",
                        "type": "XML Component",
                        "direction": comp['direction'],
                        "bbox": norm_bbox,
                        "command": intent_cmd
                    })
                    print(f"     [组件] 指令生成: {intent_cmd}")

            # --- 来源 2：让 VLM 补充视觉上的大滑动区域 ---
            print(f"  -> 正在调用 VLM 分析纯视觉的可滑动区域 (Regions)...")
            vlm_regions = self.vlm.analyze_slidable_regions(live_img_path)
            if vlm_regions:
                all_swipe_candidates.extend(vlm_regions)
                
            if not all_swipe_candidates:
                print(f"  -> 当前画面未发现任何滑动目标，跳过。")
                continue

            print(f"  => 汇总完成，该页面实时产生 {len(all_swipe_candidates)} 个测试目标。")

            # 遍历刚才分析出的 candidates 尝试滑动
            for idx, candidate in enumerate(all_swipe_candidates):
                # 只有在测第二个候选时，才需要重新回放以保证处于页面的初始状态
                if idx > 0:
                    print(f"\n    -> 重置状态，重新前往目标页面...")
                    if not self.controller.replay_trajectory_unverified(self.package, trajectory):
                        print(f"  -> ❌ 回放时跳出了目标 App ，跳过此页面。")
                        continue
                        
                self.validate_swipe(idx, candidate, page_id)

        print(f"\n=== Phase 2 完成！共合成 {len(self.successful_swipes)} 条数据。 ===")

    def validate_swipe(self, idx, candidate, page_id):
        print(f"\n[执行 {idx+1}] {candidate.get('category')} | 意图: {candidate.get('command')}")
        
        # 步骤 B：执行滑动前的截图
        before_img = str(self.output_dir / "temp_before.png")
        self.controller.take_screenshot(before_img)
        
        # 步骤 C：执行滑动
        swipe_params = self.controller.swipe_by_normalized_bbox(
            bbox=candidate['bbox'],
            direction=candidate['direction']
        )
        
        # 步骤 D：执行滑动后的截图
        after_img = str(self.output_dir / "temp_after.png")
        self.controller.take_screenshot(after_img)
        
        # 步骤 E：对比验证
        is_success = calculate_image_diff(before_img, after_img, threshold=0.01)
        
        if is_success:
            print("    -> ✅ 验证成功！保存数据。")
            dataset_id = f"{page_id}_swipe_{idx}"
            final_before = self.output_dir / f"{dataset_id}_before.png"
            final_after = self.output_dir / f"{dataset_id}_after.png"
            
            shutil.move(before_img, final_before)
            shutil.move(after_img, final_after)

            sx, sy = swipe_params['start']
            ex, ey = swipe_params['end'] 

            action = {
                "action": "swipe",
                "bbox": candidate['bbox'],
                "instruction": candidate.get('command', ''),
                "start": convert([sx, sy]),
                "end": convert([ex, ey]),
                "duration": swipe_params['duration'],
                # "direction": 默认不标记，后续根据坐标变化补充（如果是纯水平或纯垂直滑动的话） 
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

    def save_dataset(self):
        out_file = self.output_dir / "swipe_dataset.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(self.successful_swipes, f, ensure_ascii=False, indent=2)
        print(f"当前已成功合成 {len(self.successful_swipes)} 条滑动数据，保存至: {out_file}")