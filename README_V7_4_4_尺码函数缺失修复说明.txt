当前版本：V7.4.4

修复内容：
V7.4.3 中 build_result 已调用 merge_size_quantity(g)，但 order_core.py 内函数定义没有写入成功，导致：
name 'merge_size_quantity' is not defined

本版修复：
1. 强制在 order_core.py 中加入 normalize_qty()
2. 强制在 order_core.py 中加入 merge_size_quantity()
3. 保留尺码按数量展开逻辑
4. self-check 增加 order_core_has_merge_size_quantity 检查

正确效果：
41码，商品数量3 -> 尺码列显示 41 41 41
