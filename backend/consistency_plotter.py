import plotly.graph_objects as go
from typing import List, Tuple, Any

class ConsistencyPlotter:
    @staticmethod
    def _has_valid_data(note, data_type):
        if note is None:
            return False
        data = getattr(note, data_type, None)
        return data is not None and not data.empty

    @staticmethod
    def generate_key_waveform_consistency_plot(
        record_notes: List[Any], 
        replay_sources: List[dict], # List of {'label': str, 'notes': list}
        key_id: int,
        total_record_count: int = None,
        record_label: str = "Record"
    ) -> go.Figure:
        """
        生成按键波形一致性分析图 (支持多算法 Replay 对比)
        """
        if not record_notes and not replay_sources:
            fig = go.Figure()
            fig.update_layout(
                title=f"Key {key_id} 没有数据",
                xaxis={"visible": False}, 
                yaxis={"visible": False},
                annotations=[{"text": "没有数据", "showarrow": False, "font": {"size": 20}}]
            )
            return fig
            
        fig = go.Figure()
        
        # 颜色列表 (用于区分不同算法的 Replay)
        # Record 默认蓝色
        record_color = 'rgba(31, 119, 180, 0.8)'
        # Replay 使用不同的颜色
        replay_colors = [
            'rgba(255, 127, 14, 0.8)',   # 橙
            'rgba(44, 160, 44, 0.8)',    # 绿
            'rgba(214, 39, 40, 0.8)',    # 红
            'rgba(148, 103, 189, 0.8)',  # 紫
            'rgba(140, 86, 75, 0.8)',    # 褐
            'rgba(227, 119, 194, 0.8)',  # 粉
            'rgba(127, 127, 127, 0.8)',  # 灰
            'rgba(188, 189, 34, 0.8)',   # 黄
            'rgba(23, 190, 207, 0.8)'    # 青
        ]
        
        # --- 数据收集容器 ---
        # rec_wave_x, rec_wave_y, rec_wave_text = [], [], [] # Moved to section 1
        # rep_wave_x, rep_wave_y, rep_wave_text = [], [], [] # Moved to section 2
        
        # rec_ham_x, rec_ham_y, rec_ham_text = [], [], [] # Moved to section 1
        # rep_ham_x, rep_ham_y, rep_ham_text = [], [], [] # Moved to section 2

        def append_waveform(x_list, y_list, text_list, x_data, y_data, text_data):
            x_list.extend(x_data)
            x_list.append(None)
            y_list.extend(y_data)
            y_list.append(None)
            text_list.extend(text_data)
            text_list.append("")
            
        # --- 1. 绘制 Record ---
        rec_wave_x, rec_wave_y, rec_wave_text = [], [], []
        rec_ham_x, rec_ham_y, rec_ham_text = [], [], []

        record_notes.sort(key=lambda n: n.offset)
        for i, note in enumerate(record_notes):
            idx = getattr(note, 'global_sequence', i + 1)
            uuid_str = getattr(note, 'uuid', 'N/A')
            
            if ConsistencyPlotter._has_valid_data(note, 'after_touch'):
                data = note.after_touch.sort_index()
                times = ((data.index + note.offset) / 10.0).tolist()
                vals = data.values.tolist()
                texts = [f"序号: {idx}<br>UUID: {uuid_str}" for _ in times]
                append_waveform(rec_wave_x, rec_wave_y, rec_wave_text, times, vals, texts)

            if ConsistencyPlotter._has_valid_data(note, 'hammers'):
                hammers = note.hammers.sort_index()
                h_times = ((hammers.index + note.offset) / 10.0).tolist()
                h_vals = hammers.values.tolist()
                h_texts = [f"序号: {idx}<br>UUID: {uuid_str}<br>Vel: {v}" for v in h_vals]
                rec_ham_x.extend(h_times)
                rec_ham_y.extend(h_vals)
                rec_ham_text.extend(h_texts)

        # 添加 Record Trace
        if rec_wave_x:
            fig.add_trace(go.Scattergl(
                x=rec_wave_x, y=rec_wave_y,
                mode='lines+markers',
                line=dict(color=record_color, width=1.5),
                marker=dict(size=4, color=record_color),
                name=record_label,
                text=rec_wave_text,
                hovertemplate=f"<b>{record_label}</b><br>时间: %{{x:.1f}} ms<br>压力: %{{y}}<br>%{{text}}<extra></extra>"
            ))
        if rec_ham_x:
            fig.add_trace(go.Scattergl(
                x=rec_ham_x, y=rec_ham_y,
                mode='markers',
                marker=dict(color='darkblue', symbol='circle', size=8),
                name=f"{record_label} Hammer",
                text=rec_ham_text,
                hovertemplate=f"<b>{record_label} Hammer</b><br>时间: %{{x:.1f}} ms<br>锤速: %{{y}}<br>%{{text}}<extra></extra>"
            ))

        # --- 2. 绘制各路 Replay ---
        all_replay_notes = []
        for s_idx, source in enumerate(replay_sources):
            label = source.get('label', f"Replay {s_idx+1}")
            notes = source.get('notes', [])
            color = replay_colors[s_idx % len(replay_colors)]
            
            rep_wave_x, rep_wave_y, rep_wave_text = [], [], []
            rep_ham_x, rep_ham_y, rep_ham_text = [], [], []
            
            notes.sort(key=lambda n: n.offset)
            for i, note in enumerate(notes):
                idx = getattr(note, 'global_sequence', i + 1)
                uuid_str = getattr(note, 'uuid', 'N/A')
                
                if ConsistencyPlotter._has_valid_data(note, 'after_touch'):
                    data = note.after_touch.sort_index()
                    times = ((data.index + note.offset) / 10.0).tolist()
                    vals = data.values.tolist()
                    texts = [f"序号: {idx}<br>UUID: {uuid_str}" for _ in times]
                    append_waveform(rep_wave_x, rep_wave_y, rep_wave_text, times, vals, texts)

                if ConsistencyPlotter._has_valid_data(note, 'hammers'):
                    hammers = note.hammers.sort_index()
                    h_times = ((hammers.index + note.offset) / 10.0).tolist()
                    h_vals = hammers.values.tolist()
                    h_texts = [f"序号: {idx}<br>UUID: {uuid_str}<br>Vel: {v}" for v in h_vals]
                    rep_ham_x.extend(h_times)
                    rep_ham_y.extend(h_vals)
                    rep_ham_text.extend(h_texts)
            
            all_replay_notes.extend(notes) # Collect all replay notes for range calculation

            if rep_wave_x:
                fig.add_trace(go.Scattergl(
                    x=rep_wave_x, y=rep_wave_y,
                    mode='lines+markers',
                    line=dict(color=color, width=1.5),
                    marker=dict(size=4, color=color),
                    name=label,
                    text=rep_wave_text,
                    hovertemplate=f"<b>{label}</b><br>时间: %{{x:.1f}} ms<br>压力: %{{y}}<br>%{{text}}<extra></extra>"
                ))
            if rep_ham_x:
                fig.add_trace(go.Scattergl(
                    x=rep_ham_x, y=rep_ham_y,
                    mode='markers',
                    marker=dict(color=color, symbol='star', size=10),
                    opacity=0.6,
                    name=f"{label} Hammer",
                    text=rep_ham_text,
                    hovertemplate=f"<b>{label} Hammer</b><br>时间: %{{x:.1f}} ms<br>锤速: %{{y}}<br>%{{text}}<extra></extra>"
                ))

        disp_rec_count = total_record_count if total_record_count is not None else len(record_notes)
        disp_rep_count = sum(len(source.get('notes', [])) for source in replay_sources)

        # 构造标题
        title = f'Key {key_id} 波形一致性分析'
        if disp_rec_count > 0:
            title += f' (Record: {disp_rec_count}, Replay: {disp_rep_count})'
        else:
            title += f' (Replay: {disp_rep_count})'

        # 范围计算
        all_starts = sorted([n.offset/10.0 for n in record_notes + all_replay_notes if hasattr(n, 'offset')])
        start_ms = all_starts[0] - 50 if all_starts else 0
        end_ms = all_starts[min(len(all_starts)-1, 15)] + 500 if all_starts else 5000

        fig.update_layout(
            title=title,
            xaxis=dict(title='时间 (ms)', range=[start_ms, end_ms]),
            yaxis=dict(title='触后值 / 锤速'),
            template='plotly_white',
            hovermode='closest',
            height=800,
            margin=dict(l=60, r=40, t=80, b=60),
            showlegend=True
        )
        
        return fig
