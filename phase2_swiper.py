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
            self.vlm = LocalVLMClient(model_path=r"D:\Games\Qwen3-VL-4B-Instruct")
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
        self.progress_file = self.output_dir / "phase2_progress.json"

        self.successful_swipes =[]
        self.processed_pages = set()

        self._load_resume_data()

    def _load_resume_data(self):
        """加载断点续传数据"""
        if self.dataset_file.exists():
            try:
                with open(self.dataset_file, 'r', encoding='utf-8') as f:
                    self.successful_swipes = json.load(f)
                logging.info(f"  -> 📦 发现已有数据集，已恢复 {len(self.successful_swipes)} 条滑动数据。")
            except Exception as e:
                logging.error(f"  -> ⚠️ 读取已有数据集失败: {e}")

        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    self.processed_pages = set(json.load(f))
                logging.info(f"  -> 📦 发现已有进度，已自动跳过 {len(self.processed_pages)} 个处理完毕的页面。")
            except Exception as e:
                logging.error(f"  -> ⚠️ 读取进度文件失败: {e}")

    def save_progress(self, page_id):
        """将处理完毕的页面存入进度文件"""
        self.processed_pages.add(page_id)
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.processed_pages), f, ensure_ascii=False, indent=2)

    def load_memory(self):
        # Phase 1 骨架构建完成后的页面存档路径
        memory_file = Path("outputs") / self.package / "memory_graph.json"
        if not memory_file.exists():
            raise FileNotFoundError(f"找不到 Phase 1 的地图数据: {memory_file}")
        with open(memory_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_swipe_candidates(self, page_id):
        """获取当前页面的滑动候选目标，来源于 XML 组件和 VLM 视觉分析"""

        # 当场截取当前实时画面
        live_img_path = str(self.temp_dir / f"live_{page_id}.png")
        self.controller.take_screenshot(live_img_path)

        all_swipe_candidates =[]

        # --- 来源 1：提取 Phase 1 中 XML 找到的组件 ---
        logging.info(f"  -> 正在当场提取实时 XML 组件...")
        xml_components = self.controller.get_scrollable_elements_xml()

        if xml_components:
            logging.info(f"  -> 发现 {len(xml_components)} 个 XML 可滑动组件，请求意图指令...")
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
                logging.info(f"     [组件] 指令生成: {intent_cmd}")

        # --- 来源 2：让 VLM 补充视觉上的大滑动区域 ---
        logging.info(f"  -> 正在调用 VLM 分析纯视觉的可滑动区域 (Regions)...")
        vlm_regions = self.vlm.analyze_slidable_regions(live_img_path)
        if vlm_regions:
            all_swipe_candidates.extend(vlm_regions)

        logging.info(f"  => 汇总完成，该页面实时产生 {len(all_swipe_candidates)} 个测试目标。")
        return all_swipe_candidates

    def run_synthesis(self):
        logging.info(f"=== 启动 Phase 2 滑动数据合成流水线 (App: {self.package}) ===")
        pages = self.load_memory()
        logging.info(f"已加载 {len(pages)} 个独立页面进行评估。")

        for page in pages:
            page_id = page['page_id']

            # 断点续传
            if page_id in self.processed_pages:
                logging.info(f"--- ⏭️ 节点 {page_id} 此前已处理完毕，自动跳过 ---")
                continue

            img_path = page['image_path']
            trajectory = page['trajectory']

            logging.info(f"\n==================================================")
            logging.info(f"--- 正在处理节点: {page_id} / {len(pages)} ---")

            # 先通过轨迹到达目标页面 (关闭强校验，适应动态内容)
            logging.info(f"  -> 正在沿着轨迹前往目标页面...")
            if not self.controller.replay_trajectory_unverified(self.package, trajectory):
                logging.error(f"  -> ❌ 回放时跳出了目标 App ，跳过此页面。")
                continue

            # 【防抖补丁 1】：让 VLM 分析前，确保页面彻底加载出内容
            self.controller.wait_for_loading_to_finish()

            swipe_candidates = self.get_swipe_candidates(page_id)

            for idx, candidate in enumerate(swipe_candidates): # 注意：这里的 idx 是针对每个页面独立计数的，确保了即使中途重启也不会重复执行同一个目标
                if idx > 0:
                    logging.info(f"\n    -> 重置状态，重新前往目标页面...")
                    if not self.controller.replay_trajectory_unverified(self.package, trajectory):
                        logging.error(f"  -> ❌ 回放时跳出了目标 App ，跳过此页面。")
                        continue
                self.validate_swipe(idx, candidate, page_id)

            # === 【断点续传：页面完结记录】 ===
            # 当这个页面的所有 candidates 都测完后，记录该页面彻底完成
            self.save_progress(page_id)
            logging.info(f"  => 节点 {page_id} 所有的滑动评估已完成，进度已保存。")

        logging.info(f"\n=== Phase 2 完成！共合成 {len(self.successful_swipes)} 条数据。 ===")

    def validate_swipe(self, idx, candidate, page_id):
        logging.info(f"\n[执行 {idx+1}] {candidate.get('category')} | 意图: {candidate.get('command')}")

        # 【防抖补丁 2】在截取滑动前的参照图之前，必须保证页面已经彻底没有在 Loading 状态了
        self.controller.wait_for_loading_to_finish()

        # 步骤 B：执行滑动前的截图
        before_img = str(self.output_dir / "temp_before.png")
        self.controller.take_screenshot(before_img)

        # 步骤 C：执行滑动
        swipe_params = self.controller.swipe_by_normalized_bbox(
            bbox=candidate['bbox'],
            direction=candidate['direction']
        )

        # 步骤 D：执行滑动后的截图
        # 滑动后通常会拉取新数据，为了确保新数据渲染出来能被 diff 侦测到，
        # 在这里也等一下加载！
        self.controller.wait_for_loading_to_finish(timeout=4)
        after_img = str(self.output_dir / "temp_after.png")
        self.controller.take_screenshot(after_img)

        # 步骤 E：对比验证
        is_success = calculate_image_diff(before_img, after_img, threshold=0.01)

        if is_success:
            logging.info(f"    -> ✅ 验证成功！保存数据。")
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

            if sx == ex:    # x不变，竖向滑动
                action['direction'] = "up" if sy > ey else "down"
            elif sy == ey:  # y不变，横向滑动
                action['direction'] = "left" if sx > ex else "right"
            else:           # 并非纯水平或垂直滑动，暂不标记
                pass

            self.successful_swipes.append(
                {"img_filename": str(final_before), "action_data": action}
            )
            self.save_dataset()
        else:
            logging.info(f"    -> ❌ 验证失败！滑动后页面无变化。丢弃该数据。")

    def save_dataset(self):
        # 基于文件名去重，防止断点续传产生重复数据
        unique_swipes = {s['img_filename']: s for s in self.successful_swipes}
        self.successful_swipes = list(unique_swipes.values())

        with open(self.dataset_file, 'w', encoding='utf-8') as f:
            json.dump(self.successful_swipes, f, ensure_ascii=False, indent=2)
        logging.info(f"当前已成功合成 {len(self.successful_swipes)} 条滑动数据，保存至: {self.dataset_file}")

if __name__ == "__main__":
    target_app = "com.twitter.android"
    swiper = Phase2Swiper(package_name=target_app, use_local_vlm=False)
    swiper.run_synthesis()
