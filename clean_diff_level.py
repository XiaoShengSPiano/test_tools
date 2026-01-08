#!/usr/bin/env python3
# -*- coding: utf-8 -*-

with open('ui/layout_components.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 删除列定义
content = content.replace('{"name": "差异等级", "id": "diff_level", "type": "text"}', '')

# 删除tooltip
content = content.replace('"diff_level": "差异显著程度"', '')

# 删除数据处理代码
content = content.replace('diff_level = "significant"', '')
content = content.replace('diff_level = "large"', '')
content = content.replace('diff_level = "medium"', '')
content = content.replace('"diff_level": diff_level', '')

with open('ui/layout_components.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('清理完成')


