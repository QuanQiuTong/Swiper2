from phase1_explorer import Phase1Explorer
from phase2_swiper import Phase2Swiper

from utils.packages import PACKAGE_ANDROID_WORLD, PACKAGE_NEW, PACKAGE_HOT_GLOBAL, PACKAGE_HOT_CN, PACKAGE_INSTALLED

for name, pkg in PACKAGE_INSTALLED.items():
    print(f"\n=== 探索应用: {name} ({pkg}) ===")
    explorer = Phase1Explorer(package_name=pkg, max_depth=2)
    explorer.run_exploration()

    print(f"\n=== 合成滑动数据: {name} ({pkg}) ===")
    swiper = Phase2Swiper(package_name=pkg, use_local_vlm=False)
    swiper.run_synthesis()
