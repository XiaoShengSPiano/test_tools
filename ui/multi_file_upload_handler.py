#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多文件上传处理器

负责处理多算法模式下的文件上传逻辑，包括文件列表生成、文件ID管理等。
"""

import time
import hashlib
import traceback
import os
from typing import List, Dict, Any, Tuple, Optional
import dash_bootstrap_components as dbc
from dash import html, dcc, no_update

from utils.logger import Logger
from backend.file_upload_service import FileUploadService

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
    _instance = None

    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(MultiFileUploadHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化多文件上传处理器（只在第一次创建时执行）"""
        if not self._initialized:
            self._initialized = True
    
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
    
    def create_file_card(self, file_id: str, filename: str, existing_record: Optional[Dict] = None) -> dbc.Card:
        """
        创建文件卡片UI组件，支持已存在记录检测
        """
        # 提取算法显示名称 (如果有现有记录)
        default_display_name = ""
        if existing_record:
            header_extra = [
                dbc.Badge("仓库中已存在", color="success", className="ms-2", style={'fontSize': '10px'}),
                html.Small(f" (MD5: {existing_record['file_md5'][:8]}...)", className="text-muted ms-1", style={'fontSize': '10px'})
            ]
            # 预设值为历史值
            default_motor = existing_record.get('motor_type', 'D4')
            default_algo = existing_record.get('algorithm', 'PID')
            default_piano = existing_record.get('piano_type', 'Grand')
            
            # [优化] 如果库里有，优先取库里的 filename (即上次用户输入的名字)
            default_display_name = existing_record.get('filename', '')
            
            bg_color = '#e8f5e9'  # 浅绿色背景表示已存在
            btn_text = "快速加载 (从仓库)"
        else:
            header_extra = []
            default_motor = "D4"
            default_algo = "PID"
            default_piano = "Grand"
            
            # [优化] 如果是新文件，默认提示去掉后缀后的文件名
            default_display_name = os.path.splitext(filename)[0]
            
            bg_color = '#f8f9fa'
            btn_text = "确认解析并存储"

        return dbc.Card([
            dbc.CardBody([
                # 第一行：文件名与状态
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-file", 
                                  style={'color': '#007bff', 'marginRight': '8px'}),
                            html.Span(filename, style={'fontWeight': 'bold', 'fontSize': '14px'}),
                            *header_extra
                        ])
                    ], width=12)
                ], className='mb-2'),
                
                # 第二行：元数据选择与提交
                dbc.Row([
                    # 电机类型
                    dbc.Col([
                        dbc.Select(
                            id={'type': 'motor-type-select', 'index': file_id},
                            options=[
                                {"label": "电机: D3", "value": "D3"},
                                {"label": "电机: D4", "value": "D4"},
                            ],
                            value=default_motor,
                            disabled=True if existing_record else False,
                            size='sm',
                            style={'fontSize': '11px', 'backgroundColor': '#e9ecef' if existing_record else 'white'}
                        )
                    ], width=2),
                    
                    # 算法类型
                    dbc.Col([
                        dbc.Select(
                            id={'type': 'algorithm-type-select', 'index': file_id},
                            options=[
                                {"label": "算法: PID", "value": "PID"},
                                {"label": "算法: SMC", "value": "SMC"},
                            ],
                            value=default_algo,
                            disabled=True if existing_record else False,
                            size='sm',
                            style={'fontSize': '11px', 'backgroundColor': '#e9ecef' if existing_record else 'white'}
                        )
                    ], width=2),
                    
                    # 钢琴型号
                    dbc.Col([
                        dbc.Select(
                            id={'type': 'piano-type-select', 'index': file_id},
                            options=[
                                {"label": "三角琴", "value": "Grand"},
                                {"label": "立式琴", "value": "Upright"},
                            ],
                            value=default_piano,
                            disabled=True if existing_record else False,
                            size='sm',
                            style={'fontSize': '11px', 'backgroundColor': '#e9ecef' if existing_record else 'white'}
                        )
                    ], width=2),
                    
                    # 算法显示名称
                    dbc.Col([
                        dbc.Input(
                            id={'type': 'algorithm-name-input', 'index': file_id},
                            type='text',
                            value=default_display_name,
                            readonly=True if existing_record else False,
                            style={'fontSize': '12px', 'backgroundColor': '#e9ecef' if existing_record else 'white'},
                            size='sm'
                        ),
                    ], width=4),
                    
                    # 确认按钮
                    dbc.Col([
                        dbc.Button(
                            btn_text,
                            id={'type': 'confirm-algorithm-btn', 'index': file_id},
                            color='success' if not existing_record else 'info',
                            size='sm',
                            n_clicks=0,
                            style={'width': '100%', 'fontSize': '12px'}
                        )
                    ], width=2)
                ]),
                
                # 状态显示
                html.Div([
                    html.Div(
                        id={'type': 'algorithm-status', 'index': file_id},
                        style={'fontSize': '11px', 'marginTop': '5px', 'color': '#6c757d'}
                    ),
                    dcc.Store(id={'type': 'algorithm-upload-success', 'index': file_id})
                ])
            ])
        ], className='mb-2', style={'border': '1px solid #dee2e6', 'borderRadius': '5px', 'backgroundColor': bg_color})
    
    def process_uploaded_files(
        self, 
        contents_list: List[str], 
        filename_list: List[str], 
        last_modified_list: Optional[List[int]] = None,
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
                'last_modified': [],
                'file_ids': [],  # 存储文件ID映射
                'history_hints': [] # 存储查重后的历史信息（若有）
            }
            
            # 遍历新上传的文件并生成卡片
            file_items = []

            for i, (content, filename) in enumerate(zip(contents_list, filename_list)):
                file_id = self.generate_file_id(timestamp, i)
                last_modified = last_modified_list[i] if last_modified_list and i < len(last_modified_list) else None
                
                # [新增] 计算 MD5 并查库
                existing_record = None
                if backend and backend.history_manager and content:
                    try:
                        decoded_bytes = FileUploadService.decode_base64_file_content(content)
                        if decoded_bytes:
                            file_md5 = hashlib.md5(decoded_bytes).hexdigest()
                            # 同步调用历史管理器查重
                            existing_record = backend.history_manager.get_record_by_md5(file_md5)
                            
                            # 存入缓存
                            backend.cache_temp_file(file_id, decoded_bytes)
                            new_store_data['contents'].append(None) 
                        else:
                            new_store_data['contents'].append(content)
                    except Exception as e:
                        logger.warning(f"MD5 查重失败: {e}")
                        new_store_data['contents'].append(content)
                else:
                    new_store_data['contents'].append(content)

                new_store_data['filenames'].append(filename)
                new_store_data['last_modified'].append(last_modified)
                new_store_data['file_ids'].append(file_id)
                new_store_data['history_hints'].append(existing_record)

                file_card = self.create_file_card(file_id, filename, existing_record=existing_record)
                file_items.append(file_card)

                logger.debug(f"[DEBUG]📄 添加文件到队列: {filename} (已存在={existing_record is not None})")
            
            if not file_items:
                # 没有文件
                status_text = html.Span("没有上传文件", style={'color': '#ffc107'})
                return no_update, no_update, no_update
            
            # 合并到现有的store_data（保留之前未处理的文件）
            if existing_store_data and isinstance(existing_store_data, dict):
                # 提取旧数据
                ext_contents = existing_store_data.get('contents', [])
                ext_filenames = existing_store_data.get('filenames', [])
                ext_file_ids = existing_store_data.get('file_ids', [])
                ext_hints = existing_store_data.get('history_hints', [])
                
                # 修复对齐：如果旧数据没有 hints，用 None 填充补齐
                if len(ext_hints) < len(ext_filenames):
                    ext_hints.extend([None] * (len(ext_filenames) - len(ext_hints)))

                # 合并新文件到末尾
                new_store_data['contents'] = ext_contents + new_store_data['contents']
                new_store_data['filenames'] = ext_filenames + new_store_data['filenames']
                new_store_data['last_modified'] = existing_store_data.get('last_modified', [None]*len(ext_filenames)) + new_store_data['last_modified']
                new_store_data['file_ids'] = ext_file_ids + new_store_data['file_ids']
                new_store_data['history_hints'] = ext_hints + new_store_data['history_hints']

                # 重绘所有卡片
                all_file_items = []
                for i in range(len(new_store_data['filenames'])):
                    f_id = new_store_data['file_ids'][i]
                    f_name = new_store_data['filenames'][i]
                    h_hint = new_store_data['history_hints'][i]
                    all_file_items.append(self.create_file_card(f_id, f_name, existing_record=h_hint))
                
                file_list = html.Div(all_file_items)
                total_files = len(new_store_data['filenames'])
                new_files_count = len(file_items)
                if new_files_count > 0:
                    status_text = html.Span(
                        f"已上传 {new_files_count} 个新文件（当前队列共 {total_files} 个文件）",
                        style={'color': '#17a2b8', 'fontWeight': 'bold'}
                    )
                else:
                    status_text = html.Span(f"当前队列共 {total_files} 个文件")
            else:
                # 首次上传，直接使用新数据
                file_list = html.Div(file_items)
                status_text = html.Span(
                    f"已上传 {len(file_items)} 个新文件，请完成配置", 
                    style={'color': '#17a2b8', 'fontWeight': 'bold'}
                )
            
            return file_list, status_text, new_store_data
            
        except Exception as e:
            logger.error(f"❌ 处理多文件上传失败: {e}")
            
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

