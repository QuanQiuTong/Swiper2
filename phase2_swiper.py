import json
import time
import shutil
import os
import logging
from pathlib import Path
from core.device_controller import UIAutomatorController
from utils.image_utils import convert, calculate_image_diff

class Phase2Swiper:
    def __init__(self, package_name: str, use_local_vlm=True):
        self.package = package_name
        self.controller = UIAutomatorController()

        if use_local_vlm:
            from core.local_vlm import LocalVLMClient
            self.vlm = LocalVLMClient(model_path="Qwen/Qwen3-VL-4B-Instruct")
        else:
            from core.vlm_client import VLMClient
            self.vlm = VLMClient(server_url="http://127.0.0.1:8000")

        # Phase 2 成功执行并验证的滑动数据集输出目录
        self.output_dir = Path("outputs") / f"{self.package}_dataset"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.temp_dir = Path("outputs") / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # === 【断点续传核心变量】 ===
        self.dataset_file = self.output_dir / "swipe_dataset.json"
        self.click_dataset_file = self.output_dir / "click_dataset.json" # 点击数据集存储
        self.progress_file = self.output_dir / "phase2_progress.json"

        self.successful_swipes =[]
        self.successful_clicks =[] # 点击数据集列表
        self.processed_pages = set()

        self._load_resume_data()

    def _load_resume_data(self):
        """加载断点续传数据"""
        if self.dataset_file.exists():
            try:
                with open(self.dataset_file, 'r', encoding='utf-8') as f:
                    self.successful_swipes = json.load(f)
                logging.info(f"  -> 📦 Found existing dataset, restored {len(self.successful_swipes)} swipe records.")
            except Exception as e:
                logging.error(f"  -> ⚠️ Failed to read existing dataset: {e}")

        # 恢复已有的点击数据
        if self.click_dataset_file.exists():
            try:
                with open(self.click_dataset_file, 'r', encoding='utf-8') as f:
                    self.successful_clicks = json.load(f)
                logging.info(f"  -> 📦 Found existing click dataset, restored {len(self.successful_clicks)} click records.")
            except Exception as e:
                logging.error(f"  -> ⚠️ Failed to read existing click dataset: {e}")

        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    self.processed_pages = set(json.load(f))
                logging.info(f"  -> 📦 Found existing progress, automatically skipped {len(self.processed_pages)} processed pages.")
            except Exception as e:
                logging.error(f"  -> ⚠️ Failed to read progress file: {e}")

    def save_progress(self, page_id):
        """将处理完毕的页面存入进度文件"""
        self.processed_pages.add(page_id)
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.processed_pages), f, ensure_ascii=False, indent=2)

    def load_memory(self):
        # Phase 1 骨架构建完成后的页面存档路径
        memory_file = Path("outputs") / self.package / "memory_graph.json"
        if not memory_file.exists():
            raise FileNotFoundError(f"Cannot find Phase 1 map data: {memory_file}")
        with open(memory_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    # 为跳转到当前页面的 Click 操作通过 VLM 提取意图，完全在电脑端本地离线完成
    def _synthesize_click_for_page(self, page, pages):
        if not page.get('trajectory'):
            return # 首页没有触发它的 click，跳过
            
        page_id = page['page_id']
        parent_page_id = page.get('parent_page_id')
        if not parent_page_id:
            return

        # 去重检查：如果当前页面对应的 click 数据已经生成过了，跳过
        if any(c.get('target_page') == page_id for c in self.successful_clicks):
            return

        # 寻找父节点
        parent_page = next((p for p in pages if p['page_id'] == parent_page_id), None)
        if not parent_page:
            return
            
        action = page['trajectory'][-1]
        cx, cy = action['x'], action['y']
        desc = action.get('desc', 'Unknown Component')
        physical_bbox = action.get('bbox')
        
        before_img = parent_page['image_path']
        after_img = page['image_path']
        
        if not os.path.exists(before_img):
            return

        logging.info(f"  -> Requesting VLM intent for Click action from {parent_page_id} to {page_id}...")
        
        # 兼容老数据
        if not physical_bbox:
            physical_bbox =[max(0, cx-20), max(0, cy-20), cx+20, cy+20]

        instruction = self.vlm.generate_intent_for_click(before_img, physical_bbox, desc)
        logging.info(f"     [Click] Generated intent: {instruction}")
        
        w, h = self.controller.window_size
        norm_bbox = [
            int(physical_bbox[0]/w*1000), int(physical_bbox[1]/h*1000),
            int(physical_bbox[2]/w*1000), int(physical_bbox[3]/h*1000)
        ]
        norm_x, norm_y = int(cx/w*1000), int(cy/h*1000)
        
        data_entry = {
            "img_filename": before_img,
            "target_page": page_id,
            "after_image": after_img,
            "action_data": {
                "action": "click",
                "bbox": norm_bbox,
                "start": convert([norm_x, norm_y]),
                "end": convert([norm_x, norm_y]),
                "instruction": instruction,
                "description": desc
            }
        }
        
        self.successful_clicks.append(data_entry)
        self.save_dataset()

    def get_swipe_candidates(self, page_id):
        """获取当前页面的滑动候选目标，来源于 XML 组件和 VLM 视觉分析"""

        # 当场截取当前实时画面
        live_img_path = str(self.temp_dir / f"live_{page_id}.png")
        self.controller.take_screenshot(live_img_path)

        all_swipe_candidates =[]

        # --- 来源 1：提取 Phase 1 中 XML 找到的组件 ---
        # logging.info(f"  -> 正在当场提取实时 XML 组件...")
        logging.info(f"  -> Extracting live XML components from current page...")
        xml_components = self.controller.get_scrollable_elements_xml()

        if xml_components:
            logging.info(f"  -> Discovered {len(xml_components)} scrollable XML components, requesting intent commands...")
            for comp in xml_components:
                intent_cmd = self.vlm.generate_intent_for_xml_component(
                    live_img_path, comp['bounds'], comp['direction'], comp['text']
                )

                # 坐标转换：把 XML 的物理坐标转成归一化坐标送进待测队列
                w, h = self.controller.window_size
                norm_bbox = [
                    int(comp['bounds'][0]/w*1000), int(comp['bounds'][1]/h*1000),
                    int(comp['bounds'][2]/w*1000), int(comp['bounds'][3]/h*1000)
                ] # norm_bbox = self.controller.bbox_relative(comp['bounds'])

                all_swipe_candidates.append({
                    "category": "component",
                    "type": "XML Component",
                    "direction": comp['direction'],
                    "bbox": norm_bbox,
                    "command": intent_cmd
                })
                logging.info(f"     [Component] Generated intent: {intent_cmd}")

        # --- 来源 2：让 VLM 补充视觉上的大滑动区域 ---
        logging.info(f"  -> Calling VLM to analyze purely visual slidable regions (Regions)...")
        vlm_regions = self.vlm.analyze_slidable_regions(live_img_path)
        if vlm_regions:
            all_swipe_candidates.extend(vlm_regions)

        logging.info(f"  => Summary complete, generated {len(all_swipe_candidates)} test targets for current page.")
        return all_swipe_candidates

    def run_synthesis(self):
        logging.info(f"=== Starting Phase 2 Swipe Data Synthesis Pipeline (App: {self.package}) ===")
        pages = self.load_memory()
        logging.info(f"Loaded {len(pages)} unique pages for evaluation.")

        for page in pages:
            page_id = page['page_id']

            # 断点续传
            if page_id in self.processed_pages:
                logging.info(f"--- ⏭️ Node {page_id} already processed, skipping ---")
                continue

            img_path = page['image_path']
            trajectory = page['trajectory']

            logging.info(f"\n==================================================")
            logging.info(f"--- Processing node: {page_id} / {len(pages)} ---")

            # 先为导致这个页面产生的 点击(Click) 动作生成意图 (完全离线)
            self._synthesize_click_for_page(page, pages)

            # 先通过轨迹到达目标页面 (关闭强校验，适应动态内容)
            logging.info(f"  -> Replaying trajectory to target page...")
            if not self.controller.replay_trajectory_unverified(self.package, trajectory):
                logging.error(f"  -> ❌ Exited target App during replay. Skipping this page.")
                continue

            # Debounce: Ensure page is fully loaded before VLM analysis
            self.controller.wait_for_loading_to_finish()
            time.sleep(8) # 额外加时，确保动态内容也加载出来了

            swipe_candidates = self.get_swipe_candidates(page_id)

            for idx, candidate in enumerate(swipe_candidates): # 注意：这里的 idx 是针对每个页面独立计数的，确保了即使中途重启也不会重复执行同一个目标
                if idx > 0:
                    logging.info(f"\n    -> Resetting state, re-navigating to target page...")
                    if not self.controller.replay_trajectory_unverified(self.package, trajectory):
                        logging.error(f"  -> ❌ Exited target App during replay. Skipping this page.")
                        continue
                self.validate_swipe(idx, candidate, page_id)

            # === 【断点续传：页面完结记录】 ===
            # 当这个页面的所有 candidates 都测完后，记录该页面彻底完成
            self.save_progress(page_id)
            logging.info(f"  => All swipe evaluations for node {page_id} completed, progress saved.")

        # 连续back回到桌面
        for _ in range(6):
            self.controller.d.press("back")
        logging.info(f"\n=== Phase 2 完成！共合成 {len(self.successful_swipes)} 条滑动数据，{len(self.successful_clicks)} 条点击数据。 ===")

    def validate_swipe(self, idx, candidate, page_id):
        logging.info(f"\n[Executing {idx+1}] {candidate.get('category')} | Intent: {candidate.get('command')}")

        # 【防抖补丁 2】在截取滑动前的参照图之前，必须保证页面已经彻底没有在 Loading 状态了
        time.sleep(8)
        self.controller.wait_for_loading_to_finish()

        # 步骤 B：执行滑动前的截图 (此时底层的 controller 已经同时生成了 temp_before.xml)
        before_img = str(self.output_dir / "temp_before.png")
        before_xml = str(self.output_dir / "temp_before.xml")
        self.controller.take_screenshot(before_img)

        # 步骤 C：执行滑动
        swipe_params = self.controller.swipe_by_normalized_bbox(
            bbox=candidate['bbox'],
            direction=candidate['direction']
        )

        # 步骤 D：执行滑动后的截图 (同样生成了 temp_after.xml)
        # 滑动后通常会拉取新数据，为了确保新数据渲染出来能被 diff 侦测到，在这里也等一下加载！
        self.controller.wait_for_loading_to_finish(timeout=4)
        after_img = str(self.output_dir / "temp_after.png")
        after_xml = str(self.output_dir / "temp_after.xml")
        self.controller.take_screenshot(after_img)

        # 步骤 E：对比验证
        is_success = calculate_image_diff(before_img, after_img, threshold=0.01)

        if is_success:
            logging.info(f"    -> ✅ Verification passed! Saving data (Images and XML).")
            dataset_id = f"{page_id}_swipe_{idx}"
            
            final_before_img = self.output_dir / f"{dataset_id}_before.png"
            final_before_xml = self.output_dir / f"{dataset_id}_before.xml"
            final_after_img = self.output_dir / f"{dataset_id}_after.png"
            final_after_xml = self.output_dir / f"{dataset_id}_after.xml"

            # 移动图片和 XML 到正式目录并重命名
            shutil.move(before_img, final_before_img)
            shutil.move(after_img, final_after_img)
            shutil.move(before_xml, final_before_xml)
            shutil.move(after_xml, final_after_xml)

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

            if sx == ex:    # x不变，竖向滑动
                action['direction'] = "up" if sy > ey else "down"
            elif sy == ey:  # y不变，横向滑动
                action['direction'] = "left" if sx > ex else "right"
            else:           # 并非纯水平或垂直滑动，暂不标记
                pass

            self.successful_swipes.append(
                {"img_filename": str(final_before_img), "action_data": action}
            )
            self.save_dataset()
        else:
            logging.info(f"    -> ❌ Verification failed! No UI changes after swipe. Discarding data.")
            # 验证失败时清理掉没用的临时文件，保持磁盘干净
            for temp_file in[before_img, before_xml, after_img, after_xml]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

    def save_dataset(self):
        # 基于文件名去重，防止断点续传产生重复数据
        unique_swipes = {s['img_filename']: s for s in self.successful_swipes}
        self.successful_swipes = list(unique_swipes.values())

        with open(self.dataset_file, 'w', encoding='utf-8') as f:
            json.dump(self.successful_swipes, f, ensure_ascii=False, indent=2)
            
        # 【修改点】同时保存去重后的 Click 数据集
        unique_clicks = {s['target_page']: s for s in self.successful_clicks}
        self.successful_clicks = list(unique_clicks.values())
        
        with open(self.click_dataset_file, 'w', encoding='utf-8') as f:
            json.dump(self.successful_clicks, f, ensure_ascii=False, indent=2)
            
        # 这里只打印简要信息，避免频繁刷屏
        logging.info(f"Data synced and saved. Swipe: {len(self.successful_swipes)} records, Click: {len(self.successful_clicks)} records.")

if __name__ == "__main__":
    target_app = "com.twitter.android"
    swiper = Phase2Swiper(package_name=target_app, use_local_vlm=False)
    swiper.run_synthesis()