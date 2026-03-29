import time
import os
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
        print(f"=== 启动 Phase 1 纯自动化探索 (App: {self.package}) ===")
        
        queue =[]
        
        # 【断点续传】加载已有进度
        if self.memory.load_from_disk():
            print(f"  -> 📦 发现已有探索进度，成功恢复 {len(self.memory.pages)} 个页面地图！")
            # 扫描所有未满深度的页面重新加入探索队列
            for p in self.memory.pages:
                if len(p.trajectory) < self.max_depth:
                    queue.append(p.page_id)
        else:
            self.controller.reset_app(self.package)
            temp_home = str(self.temp_dir / "temp_home.png")
            self.controller.take_screenshot(temp_home)
            home_page_id = self.memory.add_page(temp_home, trajectory=[])
            print(f"记录首页: {home_page_id}")
            queue.append(home_page_id)

        while queue:
            current_page_id = queue.pop(0)
            current_page = self.memory.get_page(current_page_id)
            
            if len(current_page.trajectory) >= self.max_depth:
                continue

            print(f"\n--- 正在探索页面: {current_page_id} (深度: {len(current_page.trajectory)}) ---")
            
            # 回放处理（如果断点恢复时刚好在查 page_0，则必须主动回到首页）
            if len(current_page.trajectory) == 0:
                print(f"  -> [重置] 正在启动回到首页...")
                self.controller.reset_app(self.package)
                time.sleep(3) 
            else:
                if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                    print(f"  -> ❌ 无法稳定回放至 {current_page_id}，放弃该页面探索。")
                    continue
            
            try:
                elements = self.controller.get_clickable_elements_xml()
            except Exception as e:
                print(f"  -> ❌ ADB 通信异常或设备掉线，请重新运行脚本。错误详情: {e}")
                return # 优雅退出，进度已自动保存
                
            print(f"检测到 {len(elements)} 个可点击元素。")

            for elem in elements:
                cx, cy = elem['center']
                
                if any(abs(cx - vx) < 20 and abs(cy - vy) < 20 for vx, vy in current_page.visited_elements):
                    continue
                
                # 【核心保护】标记已点击，并立即保存进度到硬盘！
                current_page.visited_elements.add((cx, cy))
                self.memory.save_to_disk() 
                
                btn_name = elem.get('text') or elem.get('desc') or '未知组件'
                print(f"[{current_page_id}] 点击: ({cx}, {cy})[{btn_name}]")
                
                action = {'x': cx, 'y': cy, 'desc': btn_name, 'expected_image_path': ''}
                new_trajectory = current_page.trajectory + [action]

                # 采用 try-except 防止点击瞬间连接断开导致堆栈暴乱
                try:
                    self.controller.click(cx, cy, delay=1.5)
                except Exception as e:
                    print(f"  -> ❌ 点击瞬间发生崩溃或断开。请放心重启脚本，当前点已保存，下次会自动跳过。错误: {e}")
                    return

                current_pkg = self.controller.get_current_package()
                if current_pkg != self.package:
                    print(f"  -> ⚠️ 意外跳出目标应用 (当前位于: {current_pkg})。放弃该分支。")
                    if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                        break
                    continue
                
                temp_img = str(self.temp_dir / f"temp_{int(time.time())}.png")
                self.controller.take_screenshot(temp_img)
                
                is_new, matched_id = self.memory.is_new_page(temp_img)

                if is_new:
                    new_page_id = self.memory.add_page(temp_img, new_trajectory)
                    print(f"  -> ⭐ 发现新页面骨架! 记录为 {new_page_id}")

                    new_page_node = self.memory.get_page(new_page_id)
                    new_page_node.scrollable_components = self.controller.get_scrollable_elements_xml()
                    print(f"     已提取并保存 {len(new_page_node.scrollable_components)} 个 XML 可滑动组件。")
                    
                    action['expected_image_path'] = new_page_node.image_path
                    self.memory.save_to_disk() # 新页面也立刻保存
                    queue.append(new_page_id)
                else:
                    print(f"  -> 页面未产生结构性变化 (骨架匹配到 {matched_id})")
                    matched_page_node = self.memory.get_page(matched_id)
                    action['expected_image_path'] = matched_page_node.image_path
                    self.memory.save_to_disk() # 及时保存路径关系
                    
                    # 清理临时的 png 及其附带的 xml
                    os.remove(temp_img)
                    temp_xml = temp_img.replace('.png', '.xml')
                    os.remove(temp_xml)

                # 恢复基础页面，为点击下一个元素做准备
                if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                    print("  -> ❌ 严重错误：无法恢复到基础页面，终止该页面的后续元素探索。")
                    break

        print(f"\n=== Phase 1 探索完成。共发现 {len(self.memory.pages)} 个独立结构页面 ===")

if __name__ == "__main__":
    target_app = "com.deepseek.chat"
    explorer = Phase1Explorer(package_name=target_app, max_depth=2)
    explorer.run_exploration()