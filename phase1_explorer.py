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
        
        # 专门存放点完之后的临时截图，判断完后如果是旧图就删掉，新图就挪走
        self.temp_dir = Path("outputs") / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def run_exploration(self):
        print(f"=== 启动 Phase 1 纯自动化探索 (App: {self.package}) ===")
        
        # 1. 启动并处理首页
        self.controller.reset_app(self.package)
        temp_home = str(self.temp_dir / "temp_home.png")
        self.controller.take_screenshot(temp_home)
        home_page_id = self.memory.add_page(temp_home, trajectory=[])
        print(f"记录首页: {home_page_id}")

        queue = [home_page_id]

        while queue:
            current_page_id = queue.pop(0)
            current_page = self.memory.get_page(current_page_id)
            
            if len(current_page.trajectory) >= self.max_depth:
                continue

            print(f"\n--- 正在探索页面: {current_page_id} (深度: {len(current_page.trajectory)}) ---")
            self.controller.replay_trajectory(self.package, current_page.trajectory)
            
            elements = self.controller.get_clickable_elements_xml()
            print(f"检测到 {len(elements)} 个可点击元素。")

            for elem in elements:
                cx, cy = elem['center']
                
                # 去重逻辑
                if any(abs(cx - vx) < 20 and abs(cy - vy) < 20 for vx, vy in current_page.visited_elements):
                    continue
                
                current_page.visited_elements.add((cx, cy))
                
                btn_name = elem.get('text') or elem.get('desc') or '未知组件'
                print(f"[{current_page_id}] 点击: ({cx}, {cy}) [{btn_name}]")
                
                action = {'x': cx, 'y': cy, 'desc': btn_name}
                new_trajectory = current_page.trajectory + [action]

                # 【关键修复1】探索未知区域时，点击后多等一会儿 (2.5秒)，确保转场动画和网络请求完成
                self.controller.click(cx, cy, delay=2.5)
                
                # 【关键修复2】防逃逸检查 (Escape Check)
                # 判断点击后是否跳到了桌面、其他App或广告浏览器
                current_pkg = self.controller.get_current_package()
                if current_pkg != self.package:
                    print(f"  -> ⚠️ 意外跳出目标应用 (当前位于: {current_pkg})。放弃该分支。")
                    # 直接跳过后续的截图和XML解析环节，不把桌面计入图谱
                    # 也不用担心回不去，下一次 for 循环一开始就会调用 replay_trajectory 将 App 强行拉回目标页面
                    continue
                
                # 截取临时图 (此时画面必定是加载稳定、且属于目标 App 的)
                temp_img = str(self.temp_dir / f"temp_{int(time.time())}.png")
                self.controller.take_screenshot(temp_img)
                
                # 判断骨架
                is_new, matched_id = self.memory.is_new_page(temp_img)

                if is_new:
                    # 如果是新图，add_page 内部会把它移动到正式目录并重命名为 page_X.png
                    new_page_id = self.memory.add_page(temp_img, new_trajectory)
                    print(f"  -> ⭐ 发现新页面骨架! 记录为 {new_page_id}")

                    # 提取XML里的可滑动组件
                    new_page_node = self.memory.get_page(new_page_id)
                    new_page_node.scrollable_components = self.controller.get_scrollable_elements_xml()
                    print(f"     已提取并保存 {len(new_page_node.scrollable_components)} 个 XML 可滑动组件。")
                    
                    queue.append(new_page_id)
                else:
                    print(f"  -> 页面未产生结构性变化 (骨架匹配到 {matched_id})")
                    # 旧图直接删除，保持磁盘干净
                    os.remove(temp_img)

                # 回放路径回到 current_page
                self.controller.replay_trajectory(self.package, current_page.trajectory)

        self.memory.save_to_disk()
        print(f"\n=== Phase 1 探索完成。共发现 {len(self.memory.pages)} 个独立结构页面 ===")

if __name__ == "__main__":
    target_app = "com.deepseek.chat"
    explorer = Phase1Explorer(package_name=target_app, max_depth=2)
    explorer.run_exploration()