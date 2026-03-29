from phase1_explorer import Phase1Explorer
from phase2_swiper import Phase2Swiper
from summary import summary
from utils.packages import PACKAGE_ANDROID_WORLD, PACKAGE_NEW, PACKAGE_HOT_GLOBAL, PACKAGE_HOT_CN, PACKAGE_INSTALLED

for name, pkg in PACKAGE_INSTALLED.items():
    print(f"\n=== 探索应用: {name} ({pkg}) ===")
    try:
        explorer = Phase1Explorer(package_name=pkg, max_depth=2)
        explorer.run_exploration()
    except Exception as e:
        print(f"  [错误] Phase 1 探索失败: {e}")


    # 尽力合成 Phase 1 异常之前的滑动数据
    print(f"\n=== 合成滑动数据: {name} ({pkg}) ===")
    try:
        swiper = Phase2Swiper(package_name=pkg, use_local_vlm=False)
        swiper.run_synthesis()
    except Exception as e:
        print(f"  [错误] Phase 2 合成失败: {e}")

    # 增量汇总数据到 summary 中
    summary({name: pkg})
