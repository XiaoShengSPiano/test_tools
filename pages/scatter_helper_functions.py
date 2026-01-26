"""散点图辅助函数"""
from typing import Optional, Dict, Any, Tuple
from utils.logger import Logger

logger = Logger.get_logger()


def _extract_zscore_customdata(raw_customdata: Any) -> Optional[Dict[str, Any]]:
    """
    提取和验证Z-Score散点图的customdata

    Args:
        raw_customdata: 原始customdata

    Returns:
        Optional[Dict[str, Any]]: 提取的点击数据，失败返回None
    """
    if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
        customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
    else:
        customdata = raw_customdata

    if not isinstance(customdata, list):
        logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
        return None

    if len(customdata) < 4:
        logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
        return None

    # Z-Score散点图的customdata格式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name]
    # 单算法模式: [record_index, replay_index, key_id_int, delay_ms] (4个元素)
    # 多算法模式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name] (5个元素)
    record_index = customdata[0]
    replay_index = customdata[1]
    key_id = customdata[2] if len(customdata) > 2 else None
    algorithm_name = customdata[4] if len(customdata) > 4 else None

    return {
        'record_index': record_index,
        'replay_index': replay_index,
        'key_id': key_id,
        'algorithm_name': algorithm_name
    }


def _calculate_zscore_center_time(backend, click_data: Dict[str, Any]) -> Optional[float]:
    """
    计算Z-Score散点图点击点的中心时间

    Args:
        backend: 后端实例
        click_data: 点击数据

    Returns:
        Optional[float]: 中心时间（毫秒），计算失败返回None
    """
    try:
        # 获取分析器
        if click_data.get('algorithm_name'):
            analyzer = backend.multi_algorithm_manager.get_analyzer(click_data['algorithm_name']) if backend.multi_algorithm_manager else None
        else:
            analyzer = backend._get_current_analyzer()

        if not analyzer or not analyzer.note_matcher:
            return None

        record_index = click_data['record_index']
        replay_index = click_data['replay_index']

        # 从预计算的 offset_data 中获取时间信息
        offset_data = analyzer.note_matcher.get_precision_offset_alignment_data()
        if not offset_data:
            return None

        for item in offset_data:
            if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                record_keyon = item.get('record_keyon', 0)
                replay_keyon = item.get('replay_keyon', 0)
                if record_keyon and replay_keyon:
                    return (record_keyon + replay_keyon) / 2
        return None

    except Exception as e:
        logger.warning(f"[WARNING] 计算时间信息失败: {e}")
        return None


def _create_enhanced_modal_response(detail_figure_combined: Any, point_info: Dict[str, Any], center_time_ms: Optional[float]) -> Tuple[Dict[str, Any], Any, Dict[str, Any]]:
    """
    创建增强的模态框响应（支持Z-Score特定的功能）

    Args:
        detail_figure_combined: 组合详细图表
        point_info: 点信息
        center_time_ms: 中心时间（用于跳转功能）

    Returns:
        Tuple[Dict[str, Any], Any, Dict[str, Any]]: (模态框样式, 图表组件, 点信息)
    """
    modal_style = {
        'display': 'block',
        'position': 'fixed',
        'zIndex': '9999',
        'left': '0',
        'top': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.6)',
        'backdropFilter': 'blur(5px)'
    }

    # 增强点信息，包含时间信息用于跳转
    enhanced_point_info = point_info.copy()
    enhanced_point_info['center_time_ms'] = center_time_ms

    logger.info("[OK] 增强模态框响应创建成功")
    return modal_style, detail_figure_combined, enhanced_point_info


def _parse_customdata_by_type(customdata, analysis_type):
    """根据散点图类型解析customdata"""
    import traceback
    
    try:
        if analysis_type in ['key-delay', 'zscore', 'hammer-velocity', 'key-force']:
            # 格式: [record_index, replay_index, key_id, delay_ms/velocity, algorithm_name]
            if len(customdata) < 4:
                logger.warning(f"[WARNING] {analysis_type} customdata长度不足: {len(customdata)}")
                return None
            return {
                'record_index': customdata[0],
                'replay_index': customdata[1],
                'key_id': customdata[2],
                'algorithm_name': customdata[4] if len(customdata) > 4 else None
            }
        elif analysis_type == 'relative-delay':
            # 格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
            if len(customdata) < 6:
                logger.warning(f"[WARNING] relative-delay customdata长度不足: {len(customdata)}")
                return None
            return {
                'record_index': customdata[2],
                'replay_index': customdata[3],
                'key_id': customdata[5],
                'algorithm_name': customdata[4]
            }
        else:
            logger.warning(f"[WARNING] 未知的散点图类型: {analysis_type}")
            return None
    except Exception as e:
        logger.error(f"❌ 解析customdata失败: {e}")
        traceback.print_exc()
        return None


def _handle_scatter_click_logic(click_data, analysis_type, session_id, session_manager):
    """处理散点图点击的核心逻辑"""
    from dash import no_update, dcc
    import traceback

    logger.info(f"🖱️ 散点图点击: 类型={analysis_type}")

    if not click_data or 'points' not in click_data or len(click_data['points']) == 0:
        logger.warning("[WARNING] 散点图点击 - 无效的点击数据")
        return no_update, no_update

    point = click_data['points'][0]
    if not point.get('customdata'):
        logger.warning("[WARNING] 散点图点击 - 点没有customdata")
        return no_update, no_update

    raw_customdata = point['customdata']

    backend = session_manager.get_backend(session_id)
    if not backend:
        logger.warning("[WARNING] 没有找到backend")
        return no_update, no_update

    try:
        # 特殊处理Z-Score散点图
        if analysis_type == 'zscore':
            return _handle_zscore_scatter_click(raw_customdata, backend)

        # 其他散点图类型的通用处理
        customdata = raw_customdata[0] if isinstance(raw_customdata, list) and len(raw_customdata) > 0 and isinstance(raw_customdata[0], list) else raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] 散点图点击 - customdata不是列表: {type(customdata)}")
            return no_update, no_update

        click_info = _parse_customdata_by_type(customdata, analysis_type)
        if not click_info:
            return no_update, no_update

        record_index = click_info['record_index']
        replay_index = click_info['replay_index']
        algorithm_name = click_info.get('algorithm_name')
        key_id = click_info.get('key_id')

        logger.info(f"📊 解析结果: algorithm={algorithm_name}, key={key_id}, record_idx={record_index}, replay_idx={replay_index}")

        if algorithm_name:
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name, record_index=record_index, replay_index=replay_index)
        else:
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=record_index, replay_index=replay_index)

        if detail_figure_combined:
            modal_style = {'display': 'block', 'position': 'fixed', 'zIndex': '1000', 'left': '0', 'top': '0',
                          'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.6)', 'backdropFilter': 'blur(5px)'}
            modal_content = dcc.Graph(figure=detail_figure_combined, style={'height': '700px'})
            logger.info("✅ 散点图详情模态框已打开")
            return modal_style, modal_content
        else:
            logger.warning("[WARNING] 图表生成失败")
            return no_update, no_update
    except Exception as e:
        logger.error(f"❌ 处理散点图点击失败: {e}")
        traceback.print_exc()
        return no_update, no_update


def _handle_zscore_scatter_click(raw_customdata, backend):
    """专门处理Z-Score散点图的点击逻辑"""
    from dash import dcc, no_update

    logger.info("🔍 处理Z-Score散点图点击")

    # 提取Z-Score特定的customdata
    click_data = _extract_zscore_customdata(raw_customdata)
    if not click_data:
        logger.warning("[WARNING] Z-Score点击数据提取失败")
        return no_update, no_update, no_update, no_update

    record_index = click_data['record_index']
    replay_index = click_data['replay_index']
    algorithm_name = click_data.get('algorithm_name')
    key_id = click_data.get('key_id')

    logger.info(f"📊 Z-Score解析结果: algorithm={algorithm_name}, key={key_id}, record_idx={record_index}, replay_idx={replay_index}")

    # 计算中心时间（用于增强功能）
    center_time_ms = _calculate_zscore_center_time(backend, click_data)

    # 生成详细曲线图
    try:
        if algorithm_name:
            # 多算法模式
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name, record_index=record_index, replay_index=replay_index)
        else:
            # 单算法模式
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=record_index, replay_index=replay_index)

        if detail_figure_combined:
            # 存储当前点击的数据点信息，用于可能的跳转功能
            point_info = {
                'algorithm_name': algorithm_name,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'key_id': key_id,
                'center_time_ms': center_time_ms  # 预先计算的时间信息
            }

            # 创建增强的模态框响应
            modal_style = {
                'display': 'block',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }

            modal_content = dcc.Graph(figure=detail_figure_combined, style={'height': '700px'})

            # 显示跳转按钮（因为Z-Score有时间信息）
            jump_button_style = {'display': 'inline-block'} if center_time_ms is not None else {'display': 'none'}

            logger.info("✅ Z-Score散点图详情模态框已打开（增强版）")
            return modal_style, modal_content, point_info, jump_button_style
        else:
            logger.warning("[WARNING] Z-Score图表生成失败")
            return no_update, no_update, no_update, no_update

    except Exception as e:
        logger.error(f"❌ 处理Z-Score散点图点击失败: {e}")
        import traceback
        traceback.print_exc()
        return no_update, no_update, no_update, no_update


def _handle_scatter_click_logic_enhanced(click_data, analysis_type, session_id, session_manager):
    """处理散点图点击的核心逻辑（增强版，返回4个值）"""
    from dash import no_update, dcc
    import traceback

    logger.info(f"🖱️ 散点图点击: 类型={analysis_type}")

    if not click_data or 'points' not in click_data or len(click_data['points']) == 0:
        logger.warning("[WARNING] 散点图点击 - 无效的点击数据")
        return no_update, no_update, no_update, no_update

    point = click_data['points'][0]
    if not point.get('customdata'):
        logger.warning("[WARNING] 散点图点击 - 点没有customdata")
        return no_update, no_update, no_update, no_update

    raw_customdata = point['customdata']

    backend = session_manager.get_backend(session_id)
    if not backend:
        logger.warning("[WARNING] 没有找到backend")
        return no_update, no_update, no_update, no_update

    try:
        # 特殊处理Z-Score散点图
        if analysis_type == 'zscore':
            return _handle_zscore_scatter_click(raw_customdata, backend)

        # 其他散点图类型的通用处理
        customdata = raw_customdata[0] if isinstance(raw_customdata, list) and len(raw_customdata) > 0 and isinstance(raw_customdata[0], list) else raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] 散点图点击 - customdata不是列表: {type(customdata)}")
            return no_update, no_update, no_update, no_update

        click_info = _parse_customdata_by_type(customdata, analysis_type)
        if not click_info:
            return no_update, no_update, no_update, no_update

        record_index = click_info['record_index']
        replay_index = click_info['replay_index']
        algorithm_name = click_info.get('algorithm_name')
        key_id = click_info.get('key_id')

        logger.info(f"📊 解析结果: algorithm={algorithm_name}, key={key_id}, record_idx={record_index}, replay_idx={replay_index}")

        if algorithm_name:
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name, record_index=record_index, replay_index=replay_index)
        else:
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=record_index, replay_index=replay_index)

        if detail_figure_combined:
            modal_style = {'display': 'block', 'position': 'fixed', 'zIndex': '1000', 'left': '0', 'top': '0',
                          'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.6)', 'backdropFilter': 'blur(5px)'}
            modal_content = dcc.Graph(figure=detail_figure_combined, style={'height': '700px'})
            logger.info("✅ 散点图详情模态框已打开")
            return modal_style, modal_content, None, {'display': 'none'}  # 其他类型不显示跳转按钮
        else:
            logger.warning("[WARNING] 图表生成失败")
            return no_update, no_update, no_update, no_update
    except Exception as e:
        logger.error(f"❌ 处理散点图点击失败: {e}")
        traceback.print_exc()
        return no_update, no_update, no_update, no_update
