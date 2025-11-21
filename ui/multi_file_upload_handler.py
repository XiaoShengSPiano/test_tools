#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多文件上传处理器

负责处理多算法模式下的文件上传逻辑，包括文件列表生成、文件ID管理等。
"""

import time
from typing import List, Dict, Any, Tuple, Optional
import dash_bootstrap_components as dbc
from dash import html, no_update
from utils.logger import Logger

logger = Logger.get_logger()


class MultiFileUploadHandler:
    """
    多文件上传处理器类
    
    负责处理多算法模式下的文件上传，包括：
    - 文件列表生成
    - 文件ID管理
    - 新文件检测
    - 文件数据存储
    """
    
    def __init__(self):
        """初始化多文件上传处理器"""
        logger.info("✅ MultiFileUploadHandler初始化完成")
    
    def normalize_file_lists(self, contents_list: Any, filename_list: Any) -> Tuple[List[str], List[str]]:
        """
        规范化文件列表
        
        Args:
            contents_list: 文件内容列表（可能是单个值或列表）
            filename_list: 文件名列表（可能是单个值或列表）
            
        Returns:
            Tuple[List[str], List[str]]: (规范化后的内容列表, 规范化后的文件名列表)
        """
        # 处理空值情况
        if not contents_list:
            contents_list = []
        if not filename_list:
            filename_list = []
        
        # 确保是列表类型
        if not isinstance(contents_list, list):
            contents_list = [contents_list] if contents_list else []
        if not isinstance(filename_list, list):
            filename_list = [filename_list] if filename_list else []
        
        return contents_list, filename_list
    
    def generate_file_id(self, timestamp: int, index: int) -> str:
        """
        生成唯一的文件ID
        
        Args:
            timestamp: 时间戳（毫秒）
            index: 文件索引
            
        Returns:
            str: 文件ID（格式: file-{timestamp}-{index}）
        """
        return f"file-{timestamp}-{index}"
    
    def create_file_card(self, file_id: str, filename: str) -> dbc.Card:
        """
        创建文件卡片UI组件
        
        Args:
            file_id: 文件ID
            filename: 文件名
            
        Returns:
            dbc.Card: 文件卡片组件
        """
        return dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-file", 
                                  style={'color': '#007bff', 'marginRight': '8px'}),
                            html.Span(filename, style={'fontWeight': 'bold', 'fontSize': '14px'})
                        ])
                    ], width=8),
                    dbc.Col([
                        dbc.Input(
                            id={'type': 'algorithm-name-input', 'index': file_id},
                            type='text',
                            placeholder='输入算法名称',
                            style={'fontSize': '12px', 'marginBottom': '5px'},
                            debounce=True
                        ),
                        dbc.Button(
                            "确认添加",
                            id={'type': 'confirm-algorithm-btn', 'index': file_id},
                            color='success',
                            size='sm',
                            n_clicks=0,
                            style={'width': '100%'}
                        )
                    ], width=4)
                ]),
                html.Div(
                    id={'type': 'algorithm-status', 'index': file_id},
                    style={'fontSize': '11px', 'marginTop': '5px', 'color': '#6c757d'}
                )
            ])
        ], className='mb-2', style={'border': '1px solid #dee2e6', 'borderRadius': '5px'})
    
    def process_uploaded_files(
        self, 
        contents_list: List[str], 
        filename_list: List[str], 
        existing_store_data: Optional[Dict[str, Any]] = None,
        backend: Optional[Any] = None
    ) -> Tuple[html.Div, html.Span, Dict[str, Any]]:
        """
        处理上传的文件，生成文件列表UI和更新后的store数据
        
        Args:
            contents_list: 文件内容列表
            filename_list: 文件名列表
            existing_store_data: 现有的store数据
            
        Returns:
            Tuple[html.Div, html.Span, Dict]: (文件列表UI, 状态文本, 更新后的store数据)
        """
        # 规范化文件列表
        contents_list, filename_list = self.normalize_file_lists(contents_list, filename_list)
        
        if not contents_list or not filename_list:
            return no_update, no_update, no_update
        
        try:
            # 使用时间戳创建唯一ID
            timestamp = int(time.time() * 1000)  # 毫秒级时间戳
            
            # 创建新的store数据
            new_store_data = {
                'contents': [],
                'filenames': [],
                'file_ids': []  # 存储文件ID映射
            }
            
            # 获取已处理的文件列表
            processed_files = set()
            if existing_store_data and isinstance(existing_store_data, dict):
                processed_files = set(existing_store_data.get('filenames', []))
            
            # 创建文件卡片列表
            file_items = []
            for i, (content, filename) in enumerate(zip(contents_list, filename_list)):
                # 只处理新上传的文件
                if filename not in processed_files:
                    file_id = self.generate_file_id(timestamp, i)
                    file_card = self.create_file_card(file_id, filename)
                    file_items.append(file_card)
                    
                    # 添加到新的store数据
                    new_store_data['contents'].append(content)
                    new_store_data['filenames'].append(filename)
                    new_store_data['file_ids'].append(file_id)
            
            if not file_items:
                # 没有新文件，可能是重复上传
                status_text = html.Span("没有新文件，请上传不同的文件", style={'color': '#ffc107'})
                return no_update, status_text, no_update
            
            # 合并到现有的store_data（保留之前未处理的文件）
            if existing_store_data and isinstance(existing_store_data, dict):
                existing_contents = existing_store_data.get('contents', [])
                existing_filenames = existing_store_data.get('filenames', [])
                existing_file_ids = existing_store_data.get('file_ids', [])
                
                # 获取所有已添加算法的文件名，过滤掉已添加的文件
                added_filenames = set()
                if backend and hasattr(backend, 'get_all_algorithms'):
                    try:
                        algorithms = backend.get_all_algorithms()
                        for alg_info in algorithms:
                            added_filenames.add(alg_info.get('filename', ''))
                    except Exception as e:
                        logger.warning(f"⚠️ 获取已添加算法列表失败: {e}")
                
                # 过滤掉已添加的文件，只保留未添加的文件
                filtered_existing_contents = []
                filtered_existing_filenames = []
                filtered_existing_file_ids = []
                
                for i, filename in enumerate(existing_filenames):
                    if filename not in added_filenames:
                        if i < len(existing_contents):
                            filtered_existing_contents.append(existing_contents[i])
                        filtered_existing_filenames.append(filename)
                        if i < len(existing_file_ids):
                            filtered_existing_file_ids.append(existing_file_ids[i])
                
                # 合并新文件和过滤后的旧文件
                new_store_data['contents'] = filtered_existing_contents + new_store_data['contents']
                new_store_data['filenames'] = filtered_existing_filenames + new_store_data['filenames']
                new_store_data['file_ids'] = filtered_existing_file_ids + new_store_data['file_ids']
                
                # 为所有文件（包括之前上传的，但已过滤掉已添加的）创建文件卡片
                all_file_items = []
                for i, (content, filename, file_id) in enumerate(zip(
                    new_store_data['contents'],
                    new_store_data['filenames'],
                    new_store_data['file_ids']
                )):
                    # 再次检查，确保不会显示已添加的文件
                    if filename not in added_filenames:
                        file_card = self.create_file_card(file_id, filename)
                        all_file_items.append(file_card)
                
                file_list = html.Div(all_file_items)
                total_files = len(new_store_data['filenames'])
                new_files_count = len(file_items)
                if new_files_count > 0:
                    status_text = html.Span(
                        f"已上传 {new_files_count} 个新文件（共 {total_files} 个文件），请为每个文件输入算法名称", 
                        style={'color': '#17a2b8', 'fontWeight': 'bold'}
                    )
                else:
                    status_text = html.Span(
                        f"共 {total_files} 个文件，请为每个文件输入算法名称", 
                        style={'color': '#17a2b8', 'fontWeight': 'bold'}
                    )
            else:
                # 没有现有数据，只显示新文件
                file_list = html.Div(file_items)
                status_text = html.Span(
                    f"已上传 {len(file_items)} 个新文件，请为每个文件输入算法名称", 
                    style={'color': '#17a2b8', 'fontWeight': 'bold'}
                )
            
            return file_list, status_text, new_store_data
            
        except Exception as e:
            logger.error(f"❌ 处理多文件上传失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            error_text = html.Span(f"处理失败: {str(e)}", style={'color': '#dc3545'})
            return no_update, error_text, no_update
    
    def extract_file_index_from_id(
        self, 
        file_id: str, 
        file_ids: List[str]
    ) -> Optional[int]:
        """
        从文件ID中提取文件索引
        
        Args:
            file_id: 文件ID（格式: file-{timestamp}-{index} 或 file-{index}）
            file_ids: 文件ID列表
            
        Returns:
            Optional[int]: 文件索引，如果无法解析则返回None
        """
        # 首先尝试通过file_ids列表查找
        if file_id in file_ids:
            return file_ids.index(file_id)
        
        # 兼容旧格式：file-{i} 和新格式：file-{timestamp}-{i}
        try:
            if file_id.startswith('file-'):
                parts = file_id.split('-')
                if len(parts) >= 3:
                    # 新格式：file-{timestamp}-{i}
                    return int(parts[2])
                elif len(parts) == 2:
                    # 旧格式：file-{i}
                    return int(parts[1])
            return None
        except (ValueError, IndexError):
            logger.warning(f"无法解析文件ID: {file_id}")
            return None
    
    def get_file_data_by_id(
        self, 
        file_id: str, 
        store_data: Dict[str, Any]
    ) -> Optional[Tuple[str, str]]:
        """
        根据文件ID获取文件内容和文件名
        
        Args:
            file_id: 文件ID
            store_data: store数据字典
            
        Returns:
            Optional[Tuple[str, str]]: (文件内容, 文件名)，如果找不到则返回None
        """
        if not store_data or 'contents' not in store_data or 'filenames' not in store_data:
            return None
        
        contents_list = store_data.get('contents', [])
        filename_list = store_data.get('filenames', [])
        file_ids = store_data.get('file_ids', [])
        
        # 提取文件索引
        file_index = self.extract_file_index_from_id(file_id, file_ids)
        
        if file_index is None:
            return None
        
        if file_index >= len(contents_list) or file_index >= len(filename_list):
            return None
        
        return contents_list[file_index], filename_list[file_index]

