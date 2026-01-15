"""
导航栏组件
"""
import dash_bootstrap_components as dbc
from dash import html


def create_navbar():
    """
    创建顶部导航栏
    
    Returns:
        dbc.NavbarSimple: Bootstrap导航栏组件
    """
    return dbc.NavbarSimple(
        children=[
            dbc.NavItem(
                dbc.NavLink(
                    [
                        html.I(className="fas fa-file-medical-alt me-2"),
                        html.Span("异常检测报告")
                    ], 
                    href="/", 
                    active="exact",
                )
            ),
            dbc.NavItem(
                dbc.NavLink(
                    [
                        html.I(className="fas fa-chart-waterfall me-2"),
                        html.Span("瀑布图分析")
                    ], 
                    href="/waterfall", 
                    active="exact",
                )
            ),
            dbc.NavItem(
                dbc.NavLink(
                    [
                        html.I(className="fas fa-chart-scatter me-2"),
                        html.Span("散点图分析")
                    ], 
                    href="/scatter", 
                    active="exact",
                )
            ),
        ],
        brand=[
            html.I(className="fas fa-piano me-2", style={'fontSize': '24px'}),
            html.Span("SPMID分析工具", style={'fontSize': '20px', 'fontWeight': 'bold'})
        ],
        brand_href="/",
        color="primary",
        dark=True,
        fluid=True,
        className="mb-0 shadow-sm",
        style={
            'background': 'linear-gradient(135deg, #1976d2 0%, #1565c0 100%)',
            'borderBottom': '3px solid #0d47a1'
        }
    )
