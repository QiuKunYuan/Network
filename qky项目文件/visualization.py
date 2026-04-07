import matplotlib.pyplot as plt
import networkx as nx
import seaborn as sns
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import plotly.graph_objects as go
import plotly.express as px
from matplotlib.colors import LinearSegmentedColormap
import os


class NetworkVisualizer:
    def __init__(self, output_dir: str = "outputs/figures"):
        self.output_dir = output_dir
        self.setup_plot_style()
        os.makedirs(output_dir, exist_ok=True)

    def setup_plot_style(self):
        """设置绘图风格"""
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")

        # 设置中文字体（如果需要）
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False

    def plot_network(self,
                     G: nx.Graph,
                     title: str = "作战网络",
                     node_size: int = 800,
                     figsize: Tuple[int, int] = (12, 10),
                     filename: Optional[str] = None):
        """绘制基础网络图"""
        fig, ax = plt.subplots(figsize=figsize)

        # 计算节点位置
        pos = nx.spring_layout(G, k=1, iterations=50)

        # 计算节点中心性用于着色
        degree_centrality = nx.degree_centrality(G)
        node_colors = [degree_centrality[node] for node in G.nodes()]

        # 绘制网络
        nodes = nx.draw_networkx_nodes(
            G, pos,
            node_color=node_colors,
            node_size=node_size,
            cmap=plt.cm.Reds,
            alpha=0.8,
            ax=ax
        )

        nx.draw_networkx_edges(
            G, pos,
            alpha=0.6,
            edge_color='gray',
            width=1.5,
            ax=ax
        )

        nx.draw_networkx_labels(
            G, pos,
            font_size=10,
            font_weight='bold',
            ax=ax
        )

        # 添加颜色条
        plt.colorbar(nodes, ax=ax, label='度中心性')

        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.axis('off')

        plt.tight_layout()

        # 保存图片
        if filename:
            filepath = os.path.join(self.output_dir, f"{filename}.png")
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            print(f"网络图已保存: {filepath}")

        plt.show()
        return fig, ax

    def plot_multi_layer_networks(self,
                                  networks: Dict[str, nx.Graph],
                                  figsize: Tuple[int, int] = (15, 12)):
        """绘制多层网络对比图"""
        n_layers = len(networks)
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        axes = axes.flatten()

        for idx, (layer_name, network) in enumerate(networks.items()):
            if idx >= len(axes):
                break

            ax = axes[idx]
            pos = nx.spring_layout(network)

            # 根据网络类型选择颜色
            if 'command' in layer_name.lower():
                node_color = 'lightblue'
            elif 'sensor' in layer_name.lower():
                node_color = 'lightgreen'
            elif 'communication' in layer_name.lower():
                node_color = 'lightcoral'
            else:
                node_color = 'lightgray'

            nx.draw_networkx_nodes(
                network, pos,
                node_color=node_color,
                node_size=600,
                alpha=0.8,
                ax=ax
            )

            nx.draw_networkx_edges(network, pos, alpha=0.6, ax=ax)
            nx.draw_networkx_labels(network, pos, font_size=8, ax=ax)

            ax.set_title(f"{layer_name}网络\n({len(network.nodes())}节点, {len(network.edges())}边)",
                         fontsize=12, fontweight='bold')
            ax.axis('off')

        # 隐藏多余的子图
        for idx in range(n_layers, len(axes)):
            axes[idx].axis('off')

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "multi_layer_networks.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()

        return fig

    def plot_centrality_comparison(self,
                                   centrality_df: pd.DataFrame,
                                   top_k: int = 10):
        """绘制中心性指标对比图"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        axes = axes.flatten()

        centrality_metrics = ['degree', 'betweenness', 'closeness', 'composite_centrality']

        for idx, metric in enumerate(centrality_metrics):
            if metric not in centrality_df.columns:
                continue

            ax = axes[idx]
            top_nodes = centrality_df.nlargest(top_k, metric)[metric]

            colors = plt.cm.viridis(np.linspace(0, 1, len(top_nodes)))
            bars = ax.barh(range(len(top_nodes)), top_nodes.values, color=colors)

            ax.set_yticks(range(len(top_nodes)))
            ax.set_yticklabels(top_nodes.index, fontsize=10)
            ax.set_xlabel(f'{metric}中心性', fontsize=12)
            ax.set_title(f'Top {top_k} {metric}中心性节点', fontsize=14, fontweight='bold')

            # 在条形上添加数值
            for i, (bar, value) in enumerate(zip(bars, top_nodes.values)):
                ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                        f'{value:.3f}', ha='left', va='center', fontsize=9)

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "centrality_comparison.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()

        return fig

    def plot_gravity_shift(self,
                           gravity_data: pd.DataFrame,
                           figsize: Tuple[int, int] = (12, 8)):
        """绘制重心漂移图"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)

        # 绘制影响力质量变化
        ax1.plot(gravity_data['time_step'], gravity_data['critical_mass'],
                 marker='o', linewidth=2, markersize=6, color='red')
        ax1.set_xlabel('时间步')
        ax1.set_ylabel('影响力质量')
        ax1.set_title('网络重心影响力质量变化', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # 绘制影响力半径变化
        ax2.plot(gravity_data['time_step'], gravity_data['influence_radius'],
                 marker='s', linewidth=2, markersize=6, color='blue')
        ax2.set_xlabel('时间步')
        ax2.set_ylabel('影响力半径')
        ax2.set_title('网络重心影响力半径变化', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "gravity_shift.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()

        return fig

    def create_interactive_network(self,
                                   G: nx.Graph,
                                   title: str = "交互式作战网络"):
        """创建交互式网络图（Plotly）"""
        pos = nx.spring_layout(G)

        edge_x = []
        edge_y = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=1, color='gray'),
            hoverinfo='none',
            mode='lines')

        node_x = []
        node_y = []
        node_text = []
        node_degree = []
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            node_text.append(f'{node}<br>度: {G.degree[node]}')
            node_degree.append(G.degree[node])

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            hoverinfo='text',
            text=[node for node in G.nodes()],
            textposition="middle center",
            marker=dict(
                showscale=True,
                colorscale='Viridis',
                size=20,
                colorbar=dict(
                    thickness=15,
                    title='节点度',
                    xanchor='left',
                    titleside='right'
                ),
                line_width=2))

        fig = go.Figure(data=[edge_trace, node_trace],
                        layout=go.Layout(
                            title=title,
                            titlefont_size=16,
                            showlegend=False,
                            hovermode='closest',
                            margin=dict(b=20, l=5, r=5, t=40),
                            annotations=[dict(
                                text="海战网络交互式可视化",
                                showarrow=False,
                                xref="paper", yref="paper",
                                x=0.005, y=-0.002)],
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                        )

        # 保存交互式图表
        filename = os.path.join(self.output_dir, "interactive_network.html")
        fig.write_html(filename)
        print(f"交互式网络图已保存: {filename}")

        return fig

    def plot_community_structure(self,
                                 G: nx.Graph,
                                 partition: Dict,
                                 title: str = "网络社区结构"):
        """绘制网络社区结构"""
        fig, ax = plt.subplots(figsize=(12, 10))

        pos = nx.spring_layout(G)

        # 为每个社区分配颜色
        communities = list(set(partition.values()))
        colors = plt.cm.Set3(np.linspace(0, 1, len(communities)))

        community_colors = {comm: colors[i] for i, comm in enumerate(communities)}

        # 绘制节点（按社区着色）
        for community in communities:
            nodes = [node for node in G.nodes() if partition[node] == community]
            nx.draw_networkx_nodes(
                G, pos, nodelist=nodes,
                node_color=[community_colors[community]] * len(nodes),
                node_size=600,
                alpha=0.8,
                ax=ax,
                label=f'社区 {community}'
            )

        # 绘制边和标签
        nx.draw_networkx_edges(G, pos, alpha=0.5, ax=ax)
        nx.draw_networkx_labels(G, pos, font_size=9, ax=ax)

        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.axis('off')
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1))

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "community_structure.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()

        return fig

    def plot_comprehensive_networks(self, networks: Dict[str, nx.Graph], figsize: Tuple[int, int] = (20, 16)):
        """绘制全面的多层网络对比图"""
        fig, axes = plt.subplots(3, 3, figsize=figsize)
        axes = axes.flatten()

        # 定义网络类型对应的颜色和布局
        network_configs = {
            'sensor_detection': {'color': 'lightgreen', 'layout': 'spring', 'title': '传感器探测网络'},
            'track_correlation': {'color': 'lightblue', 'layout': 'circular', 'title': '轨迹关联网络'},
            'task_assignment': {'color': 'orange', 'layout': 'spring', 'title': '任务分配网络'},
            'electronic_warfare': {'color': 'purple', 'layout': 'spring', 'title': '电子战网络'},
            'weapon_system': {'color': 'red', 'layout': 'spring', 'title': '武器系统网络'},
            'spatiotemporal': {'color': 'brown', 'layout': 'spring', 'title': '时空共现网络'},
            'functional': {'color': 'pink', 'layout': 'circular', 'title': '功能类型网络'},
            'integrated': {'color': 'gold', 'layout': 'spring', 'title': '综合网络'}
        }

        for idx, (layer_name, network) in enumerate(networks.items()):
            if idx >= len(axes):
                break

            ax = axes[idx]
            config = network_configs.get(layer_name, {'color': 'gray', 'layout': 'spring', 'title': layer_name})

            if len(network.nodes()) == 0:
                ax.text(0.5, 0.5, '空网络',
                        ha='center', va='center', transform=ax.transAxes, fontsize=12)
                ax.set_title(f"{config['title']}\n(空网络)", fontsize=10)
                ax.axis('off')
                continue

            # 选择布局
            if config['layout'] == 'circular':
                pos = nx.circular_layout(network)
            else:
                pos = nx.spring_layout(network, k=1.5, iterations=50)

            # 绘制网络
            self._draw_single_network(ax, network, pos, config['color'], config['title'])

        # 隐藏多余的子图
        for idx in range(len(networks), len(axes)):
            axes[idx].axis('off')

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "comprehensive_networks.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"综合网络图已保存: {filename}")
        plt.show()

        return fig

    def _draw_single_network(self, ax, network, pos, base_color, title):
        """绘制单个网络"""
        # 根据网络类型调整节点颜色和大小
        if hasattr(network, 'is_directed') and network.is_directed():
            node_colors = self._get_directed_node_colors(network, base_color)
        else:
            node_colors = self._get_undirected_node_colors(network, base_color)

        # 绘制节点
        nodes = nx.draw_networkx_nodes(
            network, pos,
            node_color=node_colors,
            node_size=400,
            alpha=0.8,
            ax=ax
        )

        # 绘制边
        if hasattr(network, 'is_directed') and network.is_directed():
            nx.draw_networkx_edges(
                network, pos,
                edge_color='gray',
                arrows=True,
                arrowsize=20,
                arrowstyle='->',
                width=1.2,
                alpha=0.6,
                ax=ax
            )
        else:
            nx.draw_networkx_edges(
                network, pos,
                edge_color='gray',
                width=1.2,
                alpha=0.6,
                ax=ax
            )

        # 绘制标签（只显示部分标签避免重叠）
        if len(network.nodes()) <= 50:  # 只在节点较少时显示标签
            nx.draw_networkx_labels(
                network, pos,
                font_size=6,
                font_weight='bold',
                ax=ax
            )

        ax.set_title(f"{title}\n({len(network.nodes())}节点, {len(network.edges())}边)",
                     fontsize=10, fontweight='bold')
        ax.axis('off')

    def _get_directed_node_colors(self, network, base_color):
        """获取有向网络的节点颜色"""
        if len(network.nodes()) == 0:
            return []

        # 计算入度和出度
        in_degrees = dict(network.in_degree())
        out_degrees = dict(network.out_degree())

        colors = []
        for node in network.nodes():
            # 根据节点的中心性角色着色
            in_deg = in_degrees.get(node, 0)
            out_deg = out_degrees.get(node, 0)

            if in_deg > out_deg:  # 主要接收信息
                colors.append('lightcoral')
            elif out_deg > in_deg:  # 主要发送信息
                colors.append('lightgreen')
            else:  # 平衡
                colors.append('lightblue')

        return colors

    def _get_undirected_node_colors(self, network, base_color):
        """获取无向网络的节点颜色"""
        if len(network.nodes()) == 0:
            return []

        try:
            degree_centrality = nx.degree_centrality(network)
            max_degree = max(degree_centrality.values()) if degree_centrality else 1

            colors = []
            for node in network.nodes():
                centrality = degree_centrality.get(node, 0)
                # 根据中心性调整颜色深浅
                intensity = 0.3 + 0.7 * (centrality / max_degree)
                colors.append(plt.cm.Reds(intensity))

            return colors
        except:
            return [base_color] * len(network.nodes())

    def plot_gravity_analysis(self, gravity_results: Dict, critical_results: Dict, figsize: Tuple[int, int] = (15, 12)):
        """绘制重心分析结果"""
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        axes = axes.flatten()

        # 1. 关键节点排名
        if 'composite_ranking' in critical_results:
            top_nodes = critical_results['composite_ranking'][:10]
            nodes = [node for node, score, _ in top_nodes]
            scores = [score for node, score, _ in top_nodes]

            axes[0].barh(range(len(nodes)), scores, color='skyblue')
            axes[0].set_yticks(range(len(nodes)))
            axes[0].set_yticklabels(nodes, fontsize=9)
            axes[0].set_xlabel('综合中心性分数')
            axes[0].set_title('Top 10 关键节点', fontweight='bold')

        # 2. 重心稳定性
        if 'stability_analysis' in gravity_results:
            stability = gravity_results['stability_analysis']
            if stability:
                labels = ['重心节点', '第二节点']
                scores = [stability.get('top_score', 0), stability.get('second_score', 0)]

                axes[1].bar(labels, scores, color=['red', 'orange'])
                axes[1].set_ylabel('中心性分数')
                axes[1].set_title(f'重心稳定性: {stability.get("stability_level", "未知")}', fontweight='bold')

        # 3. 影响力分布
        if 'influence_distribution' in gravity_results:
            influence = gravity_results['influence_distribution']
            if influence:
                labels = ['基尼系数', '集中度比率']
                values = [influence.get('gini_coefficient', 0), influence.get('concentration_ratio', 0)]

                axes[2].bar(labels, values, color=['green', 'purple'])
                axes[2].set_ylabel('数值')
                axes[2].set_title(f'分布类型: {influence.get("distribution_type", "未知")}', fontweight='bold')

        # 4. 多重心结构
        if 'multiple_centers' in gravity_results:
            multi = gravity_results['multiple_centers']
            if multi and multi.get('multiple_centers'):
                centers = multi['multiple_centers']
                labels = [f"重心{i + 1}" for i in range(len(centers))]
                scores = [score for _, score in centers]

                axes[3].pie(scores, labels=labels, autopct='%1.1f%%', startangle=90)
                axes[3].set_title('多重心结构分布', fontweight='bold')

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "gravity_analysis.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()

        return fig

    def plot_gravity_analysis(self, gravity_results: Dict, critical_results: Dict, figsize: Tuple[int, int] = (15, 12)):
        """绘制重心分析结果"""
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        axes = axes.flatten()

        # 1. 关键节点排名
        if 'composite_ranking' in critical_results:
            top_nodes = critical_results['composite_ranking'][:10]
            nodes = [node for node, score, _ in top_nodes]
            scores = [score for node, score, _ in top_nodes]

            bars = axes[0].bar(range(len(nodes)), scores, color='skyblue', alpha=0.7)
            axes[0].set_xticks(range(len(nodes)))
            axes[0].set_xticklabels(nodes, rotation=45, ha='right', fontsize=9)
            axes[0].set_ylabel('综合中心性分数')
            axes[0].set_title('Top 10 关键节点排名', fontweight='bold')

            # 添加数值标签
            for bar, score in zip(bars, scores):
                axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                             f'{score:.3f}', ha='center', va='bottom', fontsize=8)

        # 2. 重心稳定性
        if 'stability_analysis' in gravity_results:
            stability = gravity_results['stability_analysis']
            if stability:
                labels = ['重心节点', '第二节点']
                scores = [stability.get('top_score', 0), stability.get('second_score', 0)]
                colors = ['red', 'orange']

                bars = axes[1].bar(labels, scores, color=colors, alpha=0.7)
                axes[1].set_ylabel('中心性分数')
                axes[1].set_title(f'重心稳定性: {stability.get("stability_level", "未知")}', fontweight='bold')

                # 添加数值标签
                for bar, score in zip(bars, scores):
                    axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                                 f'{score:.3f}', ha='center', va='bottom', fontsize=10)

        # 3. 影响力分布
        if 'influence_distribution' in gravity_results:
            influence = gravity_results['influence_distribution']
            if influence:
                labels = ['基尼系数', '集中度比率']
                values = [influence.get('gini_coefficient', 0), influence.get('concentration_ratio', 0)]
                colors = ['green', 'purple']

                bars = axes[2].bar(labels, values, color=colors, alpha=0.7)
                axes[2].set_ylabel('数值')
                axes[2].set_title(f'影响力分布: {influence.get("distribution_type", "未知")}', fontweight='bold')

                # 添加数值标签
                for bar, value in zip(bars, values):
                    axes[2].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                                 f'{value:.3f}', ha='center', va='bottom', fontsize=10)

        # 4. 鲁棒性分析
        if 'robustness_analysis' in critical_results:
            robustness = critical_results['robustness_analysis']
            if 'removal_impact' in robustness:
                removal_data = robustness['removal_impact']
                nodes = list(removal_data.keys())[:4]  # 取前4个节点
                efficiency_changes = [removal_data[node]['efficiency_change'] for node in nodes]

                bars = axes[3].bar(nodes, efficiency_changes, color='coral', alpha=0.7)
                axes[3].set_ylabel('效率变化')
                axes[3].set_title('关键节点移除对效率的影响', fontweight='bold')
                axes[3].tick_params(axis='x', rotation=45)

                # 添加数值标签
                for bar, change in zip(bars, efficiency_changes):
                    axes[3].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                                 f'{change:.3f}', ha='center', va='bottom', fontsize=8)

        plt.tight_layout()
        filename = os.path.join(self.output_dir, "gravity_analysis.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"重心分析图已保存: {filename}")
        plt.show()

        return fig

    def create_simple_interactive_network(self, G: nx.Graph, title: str = "作战网络"):
        """创建简化的交互式网络图 - 修复版本"""
        if G.number_of_nodes() == 0:
            print("网络为空，无法创建交互式可视化")
            return None

        try:
            pos = nx.spring_layout(G, seed=42)  # 固定随机种子以获得一致布局

            # 创建边轨迹
            edge_x = []
            edge_y = []
            for edge in G.edges():
                x0, y0 = pos[edge[0]]
                x1, y1 = pos[edge[1]]
                edge_x.extend([x0, x1, None])
                edge_y.extend([y0, y1, None])

            edge_trace = go.Scatter(
                x=edge_x, y=edge_y,
                line=dict(width=1, color='gray'),
                hoverinfo='none',
                mode='lines'
            )

            # 创建节点轨迹
            node_x = []
            node_y = []
            node_text = []
            node_degree = []

            # 计算度中心性用于着色
            degree_centrality = nx.degree_centrality(G)

            for node in G.nodes():
                x, y = pos[node]
                node_x.append(x)
                node_y.append(y)
                degree = G.degree(node)
                centrality = degree_centrality.get(node, 0)
                node_text.append(f'{node}<br>度: {degree}<br>度中心性: {centrality:.3f}')
                node_degree.append(degree)

            node_trace = go.Scatter(
                x=node_x, y=node_y,
                mode='markers+text',
                hoverinfo='text',
                text=[node for node in G.nodes()],
                textposition="middle center",
                marker=dict(
                    showscale=True,
                    colorscale='Viridis',
                    size=15,
                    color=node_degree,
                    colorbar=dict(
                        thickness=15,
                        title='节点度'
                    ),
                    line=dict(width=2, color='darkgray')
                ),
                hovertext=node_text
            )

            # 创建图形 - 修复版本：使用正确的layout参数
            fig = go.Figure(data=[edge_trace, node_trace])

            # 使用update_layout方法设置布局
            fig.update_layout(
                title=dict(
                    text=title,
                    font=dict(size=16)  # 修复：使用font而不是titlefont
                ),
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20, l=5, r=5, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
            )

            # 保存交互式图表
            filename = os.path.join(self.output_dir, f"interactive_{title}.html")
            fig.write_html(filename)
            print(f"交互式网络图已保存: {filename}")

            return fig

        except Exception as e:
            print(f"创建交互式图表失败: {e}")
            import traceback
            traceback.print_exc()
            return None