# Swiper2
Swiper2 是一个 Android UI 自动化测试工具，专注于滑动交互的测试和数据收集。

- Phase 1: 快速探索App的页面
- Phase 2: 找出页面中的滑动交互并验证

## 运行
安装依赖：`pip install -r requirements.txt`，如果使用本地VLM还需要安装torch、transformers和pillow。

连接Android设备（真机或模拟器），确保adb能够识别到设备。

先在utils/packages.py中配置好要测试的APP包名，然后运行：

```bash
python explore.py
```
运行结束后，所有的截图（包括滑动前后）会保存在`./outputs/{package_name}_dataset`目录下。

```bash
python summary.py
```
summary.py会将它们整理到`./summary`目录下并重命名。只包括滑动前的截图。  
需要滑动后的截图则可以将summary.py中的SAVE_AFTER设置为True。
