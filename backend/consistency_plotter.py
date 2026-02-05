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
    def _add_note_traces(
        fig: go.Figure,
        notes: List[Any],
        label: str,
        color: str,
        hammer_symbol: str = 'circle',
        hammer_size: int = 8,
        hammer_opacity: float = 1.0
    ):
        """通用逻辑：处理音符并添加波形与锤速 Trace"""
        if not notes:
            return

        wave_x, wave_y, wave_text = [], [], []
        ham_x, ham_y, ham_text = [], [], []

        def append_waveform(x_list, y_list, text_list, x_data, y_data, text_data):
            x_list.extend(x_data)
            x_list.append(None)
            y_list.extend(y_data)
            y_list.append(None)
            text_list.extend(text_data)
            text_list.append("")

        notes.sort(key=lambda n: n.offset)
        for i, note in enumerate(notes):
            idx = getattr(note, 'global_sequence', i + 1)
            uuid_str = getattr(note, 'uuid', 'N/A')
            
            # 处理触后波形
            if ConsistencyPlotter._has_valid_data(note, 'after_touch'):
                data = note.after_touch.sort_index()
                times = ((data.index + note.offset) / 10.0).tolist()
                vals = data.values.tolist()
                texts = [f"序号: {idx}<br>UUID: {uuid_str}" for _ in times]
                append_waveform(wave_x, wave_y, wave_text, times, vals, texts)

            # 处理锤子速度点
            if ConsistencyPlotter._has_valid_data(note, 'hammers'):
                hammers = note.hammers.sort_index()
                h_times = ((hammers.index + note.offset) / 10.0).tolist()
                h_vals = hammers.values.tolist()
                h_texts = [f"序号: {idx}<br>UUID: {uuid_str}<br>Vel: {v}" for v in h_vals]
                ham_x.extend(h_times)
                ham_y.extend(h_vals)
                ham_text.extend(h_texts)

        # 添加波形 Trace
        if wave_x:
            fig.add_trace(go.Scattergl(
                x=wave_x, y=wave_y,
                mode='lines+markers',
                line=dict(color=color, width=1.5),
                marker=dict(size=4, color=color),
                name=label,
                text=wave_text,
                hovertemplate=f"<b>{label}</b><br>时间: %{{x:.1f}} ms<br>压力: %{{y}}<br>%{{text}}<extra></extra>"
            ))

        # 添加锤子 Trace
        if ham_x:
            fig.add_trace(go.Scattergl(
                x=ham_x, y=ham_y,
                mode='markers',
                marker=dict(color=color, symbol=hammer_symbol, size=hammer_size),
                opacity=hammer_opacity,
                name=f"{label} Hammer",
                text=ham_text,
                hovertemplate=f"<b>{label} Hammer</b><br>时间: %{{x:.1f}} ms<br>锤速: %{{y}}<br>%{{text}}<extra></extra>"
            ))

    @staticmethod
    def generate_key_waveform_consistency_plot(
        data_sources: List[dict], # List of {'name': str, 'record_notes': list, 'replay_notes': list}
        key_id: int,
        title_suffix: str = ""
    ) -> go.Figure:
        """
        生成按键波形一致性分析图 (支持多算法 Record & Replay 对比)
        """
        if not data_sources:
            fig = go.Figure()
            fig.update_layout(
                title=f"Key {key_id} 没有数据",
                xaxis={"visible": False}, 
                yaxis={"visible": False},
                annotations=[{"text": "没有数据", "showarrow": False, "font": {"size": 20}}]
            )
            return fig
            
        fig = go.Figure()
        
        # 颜色列表
        colors = [
            'rgba(31, 119, 180, 0.9)', 'rgba(255, 127, 14, 0.9)', 'rgba(44, 160, 44, 0.9)',
            'rgba(214, 39, 40, 0.9)', 'rgba(148, 103, 189, 0.9)', 'rgba(140, 86, 75, 0.9)',
            'rgba(227, 119, 194, 0.9)', 'rgba(127, 127, 127, 0.9)', 'rgba(188, 189, 34, 0.9)'
        ]
        
        all_notes = []
        total_rec_count = 0
        total_rep_count = 0
        record_plotted = False

        for idx, source in enumerate(data_sources):
            name = source.get('name', f"Algo {idx+1}")
            
            # 颜色分配策略优化：
            # Record (录制) 使用统一的深灰色，作为基准
            # Replay (回放) 使用 Plotly 默认色盘循环，确保对比度高 (Blue, Orange, Green, Red...)
            record_color = 'rgba(50, 50, 50, 0.8)'
            replay_color = colors[idx % len(colors)]
            
            # Record (只绘制一次)
            rec_notes = source.get('record_notes', [])
            if rec_notes and not record_plotted:
                ConsistencyPlotter._add_note_traces(
                    fig, rec_notes, "Record", record_color, hammer_symbol='circle', hammer_size=8
                )
                all_notes.extend(rec_notes)
                total_rec_count += len(rec_notes)
                record_plotted = True
            
            # Replay
            rep_notes = source.get('replay_notes', [])
            total_rep_count += len(rep_notes)
            ConsistencyPlotter._add_note_traces(
                fig, rep_notes, f"{name} Replay", replay_color, hammer_symbol='star', hammer_size=10, hammer_opacity=0.6
            )
            all_notes.extend(rep_notes)

        # 3. 布局与标题
        title = f'Key {key_id} 波形一致性{title_suffix} (Rec: {total_rec_count}, Rep: {total_rep_count})'

        # 范围计算
        all_starts = sorted([n.offset/10.0 for n in all_notes if hasattr(n, 'offset')])
        start_ms = all_starts[0] - 50 if all_starts else 0
        end_ms = all_starts[min(len(all_starts)-1, 15)] + 500 if all_starts else 5000

        fig.update_layout(
            title=title,
            xaxis=dict(title='时间 (ms)', range=[start_ms, end_ms]),
            yaxis=dict(title='触后值 / 锤速'),
            template='plotly_white',
            hovermode='closest',
            height=800,
            margin=dict(l=60, r=100, t=80, b=100),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top", y=-0.2,
                xanchor="center", x=0.5
            )
        )
        return fig
