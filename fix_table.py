#!/usr/bin/env python3
# -*- coding: utf-8 -*-

with open('ui/layout_components.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换样式条件
old_style = '''                            style_data_conditional=[
                                {
                                    "if": {"column_id": "diff_level", "filter_query": "{diff_level} = 'significant'"},
                                    "backgroundColor": "rgba(255, 193, 193, 0.3)",
                                    "color": "#dc3545",
                                    "fontWeight": "bold"
                                },
                                {
                                    "if": {"column_id": "diff_level", "filter_query": "{diff_level} = 'large'"},
                                    "backgroundColor": "rgba(255, 243, 205, 0.3)",
                                    "color": "#fd7e14",
                                    "fontWeight": "bold"
                                },
                                {
                                    "if": {"column_id": "diff_level", "filter_query": "{diff_level} = 'medium'"},
                                    "backgroundColor": "rgba(255, 255, 224, 0.3)",
                                    "color": "#ffc107"
                                }
                            ],'''

new_style = '                            style_data_conditional=[],'

content = content.replace(old_style, new_style)

# 替换filter_action
content = content.replace('filter_action="native",', 'filter_action="none",')

with open('ui/layout_components.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('修改完成')


