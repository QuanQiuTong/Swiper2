import json
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

        self.profile_file = Path("outputs") / self.package / "phase1_profile.json"
        self.profile_table_file = Path("outputs") / self.package / "phase1_profile_table.md"
        self.profile = self._new_profile()

    def _new_profile(self):
        return {
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ended_at": None,
            "counts": {
                "states_before_run": 0,
                "states_total": 0,
                "states_created_this_run": 0,
                "pages_explored_this_run": 0,
                "clickable_elements_detected": 0,
                "click_attempts": 0,
                "skipped_duplicate_clicks": 0,
                "new_states_created": 0,
                "unchanged_states_observed": 0,
                "escaped_branches": 0,
            },
            "timings": {
                "state_creation_seconds": [],
                "page_exploration_seconds": [],
                "click_attempt_seconds": [],
            },
        }

    def _record_count(self, key, value=1):
        self.profile["counts"][key] = self.profile["counts"].get(key, 0) + value

    def _record_timing(self, key, elapsed):
        self.profile["timings"].setdefault(key, []).append(round(float(elapsed), 6))

    @staticmethod
    def _avg(values):
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _fmt_seconds(seconds):
        if seconds < 1:
            return f"{seconds * 1000:.1f} ms"
        return f"{seconds:.2f} s"

    def _write_profile(self, total_elapsed, resumed_from_existing_memory):
        counts = self.profile["counts"]
        counts["states_total"] = len(self.memory.pages)

        # The table requires "GUI exploration / state collection" as seconds per state.
        # For a clean profiling run, this is Phase-1 total exploration time divided by
        # the number of collected structural GUI states.
        state_count = counts.get("states_total", 0)
        avg_per_state = total_elapsed / state_count if state_count else 0.0
        avg_new_state_creation = self._avg(self.profile["timings"].get("state_creation_seconds", []))

        summary = {
            "started_at": self.profile.get("started_at"),
            "ended_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "package": self.package,
            "max_depth": self.max_depth,
            "resumed_from_existing_memory": resumed_from_existing_memory,
            "counts": counts,
            "timings": self.profile["timings"],
            "total_exploration_seconds": round(float(total_elapsed), 6),
            "avg_gui_exploration_state_collection_seconds": round(float(avg_per_state), 6),
            "avg_new_state_creation_seconds": round(float(avg_new_state_creation), 6),
        }

        with open(self.profile_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        lines = [
            "| Module | Avg. Time |",
            "|---|---:|",
            f"| GUI exploration / state collection | {self._fmt_seconds(avg_per_state)} per state |",
            "",
            f"- Phase 1 total exploration time: {self._fmt_seconds(total_elapsed)}",
            f"- Total collected GUI states: {counts.get('states_total', 0)}",
            f"- New states created in this run: {counts.get('states_created_this_run', 0)}",
            f"- Resumed from existing memory: {resumed_from_existing_memory}",
        ]
        with open(self.profile_table_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        logging.info(f"Phase 1 profile saved to {self.profile_file} and {self.profile_table_file}.")

    def run_exploration(self):
        """Core BFS Exploration Loop"""
        logging.info(f"=== Starting Phase 1 Automated Exploration (App: {self.package}) ===")
        run_start = time.perf_counter()
        resumed_from_existing_memory = False

        queue = []

        #[Breakpoint Resume] Load existing progress
        if self.memory.load_from_disk():
            resumed_from_existing_memory = True
            self.profile["counts"]["states_before_run"] = len(self.memory.pages)
            logging.info(f"  -> 📦 Found existing progress, restored {len(self.memory.pages)} page graphs!")
            for p in self.memory.pages:
                if len(p.trajectory) < self.max_depth and not getattr(p, 'is_fully_explored', False):
                    queue.append(p.page_id)
        else:
            self.profile["counts"]["states_before_run"] = 0
            state_collect_start = time.perf_counter()
            self.controller.reset_app(self.package)
            time.sleep(8) # Wait for dynamic UI rendering

            temp_home = str(self.temp_dir / "temp_home.png")
            self.controller.take_screenshot(temp_home)
            # Home page has no parent node
            home_page_id = self.memory.add_page(temp_home, trajectory=[], parent_page_id=None)
            self._record_count("states_created_this_run")
            self._record_timing("state_creation_seconds", time.perf_counter() - state_collect_start)
            logging.info(f"Recorded Home Page: {home_page_id}")
            queue.append(home_page_id)

        while queue:
            current_page_id = queue.pop(0)
            current_page = self.memory.get_page(current_page_id)

            if len(current_page.trajectory) >= self.max_depth:
                continue

            logging.info(f"\n--- Exploring Page: {current_page_id} (Depth: {len(current_page.trajectory)}) ---")
            page_start = time.perf_counter()

            # Replay handling (actively return to home if restoring from page_0)
            if len(current_page.trajectory) == 0:
                logging.info(f"  -> [Reset] Returning to home page...")
                self.controller.reset_app(self.package)
                time.sleep(1) 
            else:
                if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                    logging.error(f"  -> ❌ Failed to stably replay trajectory to {current_page_id}, abandoning exploration of this page.")
                    self._record_timing("page_exploration_seconds", time.perf_counter() - page_start)
                    continue
            time.sleep(8) 
            self._record_count("pages_explored_this_run")

            elements = self.controller.get_clickable_elements_xml()
            self._record_count("clickable_elements_detected", len(elements))
            logging.info(f"Detected {len(elements)} clickable elements.")

            for elem in elements:
                time.sleep(8) 
                success = self._explore_single_element(elem, current_page, queue)
                if not success:
                    # Break loop if a fatal error occurs (e.g., ADB disconnect, app crash)
                    break
            else:
                # Mark page fully explored only if loop completes without breaking
                current_page.is_fully_explored = True
                self.memory.save_to_disk()

            self._record_timing("page_exploration_seconds", time.perf_counter() - page_start)

        self.memory.save_to_disk()
        total_elapsed = time.perf_counter() - run_start
        self._write_profile(total_elapsed, resumed_from_existing_memory)
        logging.info(f"\n=== Phase 1 Exploration Complete. Discovered {len(self.memory.pages)} Independent Structural Pages ===")

    def _explore_single_element(self, elem: dict, current_page, queue: list) -> bool:
        """
        Handles single element exploration (Click, Debounce, Screenshot, Verify, Replay).
        Returns False if a fatal error occurs.
        """
        cx, cy = elem['center']

        # Deduplication check
        if any(abs(cx - vx) < 20 and abs(cy - vy) < 20 for vx, vy in current_page.visited_elements):
            self._record_count("skipped_duplicate_clicks")
            return True

        self._record_count("click_attempts")
        attempt_start = time.perf_counter()

        # Mark and save progress
        current_page.visited_elements.add((cx, cy))
        self.memory.save_to_disk() 

        btn_name = elem.get('text') or elem.get('desc') or 'Unknown Component'
        logging.info(f"[{current_page.page_id}] Clicked: ({cx}, {cy}) [{btn_name}]")

        # Save bbox for Phase 2 Intent Generation
        action = {
            'x': cx, 
            'y': cy, 
            'bbox': elem['bounds'], 
            'desc': btn_name, 
            'expected_image_path': ''
        }
        new_trajectory = current_page.trajectory + [action]

        self.controller.click(cx, cy, delay=2.5)

        # Smart debounce: wait for loading to finish
        self.controller.wait_for_loading_to_finish()

        # Escape prevention check
        current_pkg = self.controller.get_current_package()
        if current_pkg != self.package:
            self._record_count("escaped_branches")
            logging.warning(f"  -> ⚠️ Unexpectedly exited target app (Current: {current_pkg}). Aborting branch.")
            if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                logging.error("  -> ❌ Fatal Error: Failed to restore to base page.")
                self._record_timing("click_attempt_seconds", time.perf_counter() - attempt_start)
                return False 
            self._record_timing("click_attempt_seconds", time.perf_counter() - attempt_start)
            return True 

        # Capture and compare new state
        temp_img = str(self.temp_dir / f"temp_{int(time.time())}.png")
        self.controller.take_screenshot(temp_img)
        is_new, matched_id = self.memory.is_new_page(temp_img)

        if is_new:
            # Pass current page ID as parent_page_id
            new_page_id = self.memory.add_page(temp_img, new_trajectory, parent_page_id=current_page.page_id)
            self._record_count("states_created_this_run")
            self._record_count("new_states_created")
            self._record_timing("state_creation_seconds", time.perf_counter() - attempt_start)
            logging.info(f"  -> ⭐ New page skeleton detected! Recorded as {new_page_id}")

            new_page_node = self.memory.get_page(new_page_id)
            new_page_node.scrollable_components = self.controller.get_scrollable_elements_xml()
            logging.info(f"     Extracted and saved {len(new_page_node.scrollable_components)} XML scrollable components.")

            action['expected_image_path'] = new_page_node.image_path
            queue.append(new_page_id)
        else:
            self._record_count("unchanged_states_observed")
            logging.info(f"  -> No structural UI changes detected (skeleton matched {matched_id})")
            matched_page_node = self.memory.get_page(matched_id)
            action['expected_image_path'] = matched_page_node.image_path

            if os.path.exists(temp_img):
                os.remove(temp_img)
            temp_xml = temp_img.replace('.png', '.xml')
            if os.path.exists(temp_xml):
                os.remove(temp_xml)

        self.memory.save_to_disk()

        # Restore initial state of the current page for the next element
        if not self.controller.replay_trajectory(self.package, current_page.trajectory):
            logging.error("  -> ❌ Fatal Error: Failed to restore to base page.")
            self._record_timing("click_attempt_seconds", time.perf_counter() - attempt_start)
            return False

        self._record_timing("click_attempt_seconds", time.perf_counter() - attempt_start)
        return True
