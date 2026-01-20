"""散点图辅助函数"""
from utils.logger import Logger

logger = Logger.get_logger()


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
    
    backend = session_manager.get_backend(session_id)
    if not backend:
        logger.warning("[WARNING] 没有找到backend")
        return no_update, no_update
    
    try:
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
