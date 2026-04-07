import time
import os
import logging
from pathlib import Path
from core.device_controller import UIAutomatorController
from core.page_graph import PageMemory

class Phase1Explorer:
    def __init__(self, package_name: str, max_depth=3):
        self.package = package_name
        self.max_depth = max_depth
        self.controller = UIAutomatorController()
        self.memory = PageMemory(package_name=self.package, similarity_threshold=0.85)
        
        self.temp_dir = Path("outputs") / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def run_exploration(self):
        """核心的 BFS 探索主循环"""
        logging.info(f"=== Starting Phase 1 Automated Exploration (App: {self.package}) ===")
        
        queue =[]
        
        # 【断点续传】加载已有进度
        if self.memory.load_from_disk():
            logging.info(f"  -> 📦 Found existing progress, restored {len(self.memory.pages)} page graphs!")
            # 扫描所有未满深度的页面重新加入探索队列
            for p in self.memory.pages:
                if len(p.trajectory) < self.max_depth and not getattr(p, 'is_fully_explored', False):
                    queue.append(p.page_id)
        else:
            self.controller.reset_app(self.package)
            time.sleep(8) # Wait for dynamic UI rendering
            
            temp_home = str(self.temp_dir / "temp_home.png")
            self.controller.take_screenshot(temp_home)
            # 【修改点】首页没有父节点，传入 parent_page_id=None
            home_page_id = self.memory.add_page(temp_home, trajectory=[], parent_page_id=None)
            logging.info(f"Recorded Home Page: {home_page_id}")
            queue.append(home_page_id)

        while queue:
            current_page_id = queue.pop(0)
            current_page = self.memory.get_page(current_page_id)
            
            if len(current_page.trajectory) >= self.max_depth:
                continue

            logging.info(f"\n--- Exploring Page: {current_page_id} (Depth: {len(current_page.trajectory)}) ---")
            
            # 回放处理（如果断点恢复时刚好在查 page_0，则必须主动回到首页）
            if len(current_page.trajectory) == 0:
                logging.info(f"  -> [Reset] Returning to home page...")
                self.controller.reset_app(self.package)
                time.sleep(1) 
            else:
                if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                    logging.error(f"  -> ❌ Failed to stably replay trajectory to {current_page_id}, abandoning exploration of this page.")
                    continue
            time.sleep(8) # Wait for dynamic UI rendering
            
            elements = self.controller.get_clickable_elements_xml()
                
            logging.info(f"Detected {len(elements)} clickable elements.")

            for elem in elements:

                time.sleep(8) # Wait for dynamic UI rendering
                success = self._explore_single_element(elem, current_page, queue)
                if not success:
                    # 如果返回 False，说明发生了致命错误（如无法回退到基础页面或 ADB 断开），中断当前页面的后续探索
                    break
            else:
                # 只有当 for 循环正常跑完（没有被 break 提前中断），才标记该页面所有组件探索完毕
                current_page.is_fully_explored = True
                self.memory.save_to_disk()

        self.memory.save_to_disk()
        logging.info(f"\n=== Phase 1 Exploration Complete. Discovered {len(self.memory.pages)} Independent Structural Pages ===")

    def _explore_single_element(self, elem: dict, current_page, queue: list) -> bool:
        """
        处理【单个可点击元素】的探索逻辑（点击、防抖、截图、对比、回放）。
        :return: True 表示继续遍历下一个元素，False 表示遇到严重错误需终止当前页面遍历。
        """
        cx, cy = elem['center']
        
         # 去重
        if any(abs(cx - vx) < 20 and abs(cy - vy) < 20 for vx, vy in current_page.visited_elements):
            return True
        
        # 标记并保存进度
        current_page.visited_elements.add((cx, cy))
        self.memory.save_to_disk() 
        
        btn_name = elem.get('text') or elem.get('desc') or 'Unknown Component'
        logging.info(f"[{current_page.page_id}] Clicked: ({cx}, {cy}) [{btn_name}]")
        
        # 把 bbox 直接存下来，供 Phase 2 生成意图使用
        action = {
            'x': cx, 
            'y': cy, 
            'bbox': elem['bounds'], 
            'desc': btn_name, 
            'expected_image_path': ''
        }
        new_trajectory = current_page.trajectory + [action]

        self.controller.click(cx, cy, delay=2.5)

        # 智能防抖：等待加载动画结束
        self.controller.wait_for_loading_to_finish()

        # 防逃逸检查
        current_pkg = self.controller.get_current_package()
        if current_pkg != self.package:
            logging.warning(f"  -> ⚠️ Unexpectedly exited target app (Current: {current_pkg}). Aborting branch.")
            if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                logging.error("  -> ❌ Fatal Error: Failed to restore to base page, terminating further exploration on this page.")
                return False # 致命错误
            return True # 成功恢复，继续下一个元素 (相当于原循环的 continue)
        
        # 截取新状态并比对
        temp_img = str(self.temp_dir / f"temp_{int(time.time())}.png")
        self.controller.take_screenshot(temp_img)
        is_new, matched_id = self.memory.is_new_page(temp_img)

        if is_new:
            # 传入当前页面 ID 作为新页面的 parent_page_id
            new_page_id = self.memory.add_page(temp_img, new_trajectory, parent_page_id=current_page.page_id)
            logging.info(f"  -> ⭐ New page skeleton detected! Recorded as {new_page_id}")

            new_page_node = self.memory.get_page(new_page_id)
            new_page_node.scrollable_components = self.controller.get_scrollable_elements_xml()
            logging.info(f"     Extracted and saved {len(new_page_node.scrollable_components)} XML scrollable components.")
            
            action['expected_image_path'] = new_page_node.image_path
            queue.append(new_page_id)
        else:
            logging.info(f"  -> No structural UI changes detected (skeleton matched {matched_id})")
            matched_page_node = self.memory.get_page(matched_id)
            action['expected_image_path'] = matched_page_node.image_path
            
            if os.path.exists(temp_img):
                os.remove(temp_img)
            temp_xml = temp_img.replace('.png', '.xml')
            if os.path.exists(temp_xml):
                os.remove(temp_xml)

        self.memory.save_to_disk()

        # 探索完当前分支，恢复到当前页面的初始状态，以便点击下一个元素
        if not self.controller.replay_trajectory(self.package, current_page.trajectory):
            logging.error("  -> ❌ Fatal Error: Failed to restore to base page, terminating further exploration on this page.")
            return False

        return True # 一切顺利，告诉 for 循环继续