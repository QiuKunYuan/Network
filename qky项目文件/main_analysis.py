# src/main_analysis.py
import os
from typing import Dict, Any

from matplotlib import pyplot as plt

from data_processor import AFSIMDataProcessor
from exp.improved_network_builder import ImprovedCombatNetworkBuilder
from critical_node_analyzer import CriticalNodeAnalyzer
from gravity_center_analyzer import GravityCenterAnalyzer
from utils import calculate_network_metrics, generate_report
from visualization import NetworkVisualizer
import numpy as np  # 添加这行
import networkx as nx  # 添加这行

class MainAnalysis:
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.processor = None
        self.networks = {}
        self.analysis_results = {}

        # 初始化分析器
        self.critical_analyzer = CriticalNodeAnalyzer()
        self.gravity_analyzer = GravityCenterAnalyzer()
        self.visualizer = NetworkVisualizer()

    # 在 MainAnalysis 类中添加这个方法
    def diagnose_network_issues(self):
        """诊断网络结构问题"""
        if 'integrated' not in self.networks:
            return

        G = self.networks['integrated']
        print("\n=== 网络结构诊断 ===")
        print(f"节点数: {G.number_of_nodes()}")
        print(f"边数: {G.number_of_edges()}")
        print(f"网络密度: {nx.density(G):.3f}")

        # 检查节点度分布
        degrees = [d for _, d in G.degree()]
        print(f"平均度: {np.mean(degrees):.1f}")
        print(f"最大度: {max(degrees)}")
        print(f"最小度: {min(degrees)}")

        # 检查前几个节点的连接情况
        print("\n前5个节点的连接情况:")
        for i, node in enumerate(list(G.nodes())[:5]):
            neighbors = list(G.neighbors(node))
            print(f"{node}: 度={G.degree(node)}, 邻居数={len(neighbors)}")
            if len(neighbors) > 5:
                print(f"  示例邻居: {neighbors[:3]}...")

        # 检查网络类型
        print(f"\n网络类型: {'有向' if G.is_directed() else '无向'}")

        # 检查边权重分布
        edge_weights = [data.get('weight', 1) for _, _, data in G.edges(data=True)]
        print(f"边权重范围: {min(edge_weights)} - {max(edge_weights)}")

    def run_comprehensive_analysis(self):
        """运行综合分析"""
        print("=" * 60)
        print("开始海战网络综合分析")
        print("=" * 60)

        try:
            # 1. 数据加载与处理
            print("\n1. 数据加载与处理...")
            self.processor = AFSIMDataProcessor(self.data_path)
            #
            # self.processor.extract_interactions(
            #     keyword1='soj',
            #     keyword2='ew_radar',
            #     output_path='soj_ew_radar_interactions.csv'
            # )

            # 2. 网络构建
            print("\n2. 网络构建...")
            network_builder = ImprovedCombatNetworkBuilder()
            self.networks = network_builder.build_comprehensive_networks(self.processor)

            # 添加网络诊断
            self.diagnose_network_issues()

            # 3. 关键节点分析（主要针对综合网络）
            print("\n3. 关键节点分析...")
            if 'integrated' in self.networks:
                integrated_network = self.networks['integrated']
                self.analysis_results['critical_nodes'] = self.critical_analyzer.comprehensive_critical_node_analysis(
                    integrated_network
                )

            # 4. 重心分析
            print("\n4. 网络重心分析...")
            if 'integrated' in self.networks:
                integrated_network = self.networks['integrated']
                self.analysis_results['gravity_analysis'] = self.gravity_analyzer.analyze_network_gravity(
                    integrated_network
                )

            # 5. 网络指标计算
            print("\n5. 网络指标计算...")
            self.analysis_results['network_metrics'] = {}
            for name, network in self.networks.items():
                self.analysis_results['network_metrics'][name] = calculate_network_metrics(network)

            # # 6. 可视化
            # print("\n6. 生成可视化...")
            # self._generate_visualizations()
            #
            # # 7. 生成报告
            # print("\n7. 生成分析报告...")
            # self._generate_reports()
            #
            # print("\n" + "=" * 60)
            # print("分析完成！")
            # print("=" * 60)
            #8. 超网分析
            self.run_hyper_network_analysis()

            return self.analysis_results

        except Exception as e:
            print(f"分析过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _generate_visualizations(self):
        """生成可视化图表 - 最终修复版本"""
        try:
            print("开始生成可视化图表...")

            # 1. 网络结构可视化
            print("生成网络拓扑图...")
            self.visualizer.plot_comprehensive_networks(self.networks)

            # 2. 关键节点可视化
            if 'critical_nodes' in self.analysis_results and 'integrated' in self.networks:
                critical_results = self.analysis_results['critical_nodes']

                # 中心性排名图
                if 'centrality_df' in critical_results:
                    print("生成中心性排名图...")
                    self.visualizer.plot_centrality_comparison(
                        critical_results['centrality_df'], top_k=15
                    )

                # 重心分析图
                if 'gravity_analysis' in self.analysis_results:
                    print("生成重心分析图...")
                    if hasattr(self.visualizer, 'plot_gravity_analysis'):
                        self.visualizer.plot_gravity_analysis(
                            self.analysis_results['gravity_analysis'],
                            critical_results
                        )

            # 3. 网络指标对比图
            print("生成网络指标对比图...")
            self._plot_network_metrics_comparison()

            # 4. 交互式可视化（带错误处理）
            print("生成交互式可视化...")
            if 'integrated' in self.networks:
                if hasattr(self.visualizer, 'create_simple_interactive_network'):
                    self.visualizer.create_simple_interactive_network(
                        self.networks['integrated'], "综合作战网络"
                    )
                else:
                    print("跳过交互式可视化: 方法不存在")

            print("所有可视化图表生成完成!")

        except Exception as e:
            print(f"可视化生成失败: {e}")
            import traceback
            traceback.print_exc()

    def _generate_reports(self):
        """生成分析报告"""
        try:
            # 关键节点报告
            if 'critical_nodes' in self.analysis_results:
                critical_report = self.critical_analyzer.generate_critical_node_report(
                    self.analysis_results['critical_nodes']
                )
                with open("outputs/reports/critical_nodes_report.md", "w", encoding="utf-8") as f:
                    f.write(critical_report)
                print("✅ 关键节点报告已生成")

            # 重心分析报告
            if 'gravity_analysis' in self.analysis_results:
                gravity_report = self.gravity_analyzer.generate_gravity_report(
                    self.analysis_results['gravity_analysis']
                )
                with open("outputs/reports/gravity_analysis_report.md", "w", encoding="utf-8") as f:
                    f.write(gravity_report)
                print("✅ 重心分析报告已生成")

            # 综合报告
            combined_results = {
                'critical_analysis': self.analysis_results.get('critical_nodes', {}),
                'gravity_analysis': self.analysis_results.get('gravity_analysis', {}),
                'network_metrics': self.analysis_results.get('network_metrics', {})
            }

            generate_report(combined_results, "comprehensive_analysis_report.md")
            print("✅ 综合分析报告已生成")

        except Exception as e:
            print(f"报告生成失败: {e}")

    def get_key_findings(self) -> Dict[str, Any]:
        """获取关键发现"""
        findings = {}

        # 关键节点发现
        if 'critical_nodes' in self.analysis_results:
            critical_results = self.analysis_results['critical_nodes']
            if 'composite_ranking' in critical_results:
                top_nodes = critical_results['composite_ranking'][:3]
                findings['top_critical_nodes'] = [
                    {'node': node, 'score': score, 'metrics': metrics}
                    for node, score, metrics in top_nodes
                ]

        # 重心分析发现
        if 'gravity_analysis' in self.analysis_results:
            gravity_results = self.analysis_results['gravity_analysis']
            if 'basic_gravity' in gravity_results:
                bg = gravity_results['basic_gravity']
                findings['gravity_center'] = {
                    'node': bg.get('gravity_node'),
                    'score': bg.get('gravity_score'),
                    'stability': gravity_results.get('stability_analysis', {}).get('stability_level')
                }

        return findings


    # 在 MainAnalysis 类中添加这个方法
    def diagnose_network_issues(self):
        """诊断网络结构问题"""
        if 'integrated' not in self.networks:
            return

        G = self.networks['integrated']
        print("\n=== 网络结构诊断 ===")
        print(f"节点数: {G.number_of_nodes()}")
        print(f"边数: {G.number_of_edges()}")
        print(f"网络密度: {nx.density(G):.3f}")

        # 检查节点度分布
        degrees = [d for _, d in G.degree()]
        print(f"平均度: {np.mean(degrees):.1f}")
        print(f"最大度: {max(degrees)}")
        print(f"最小度: {min(degrees)}")

        # 检查前几个节点的连接情况
        print("\n前5个节点的连接情况:")
        for i, node in enumerate(list(G.nodes())[:5]):
            neighbors = list(G.neighbors(node))
            print(f"{node}: 度={G.degree(node)}, 邻居数={len(neighbors)}")
            if len(neighbors) > 5:
                print(f"  示例邻居: {neighbors[:3]}...")

        # 检查网络类型
        print(f"\n网络类型: {'有向' if G.is_directed() else '无向'}")

        # 检查边权重分布
        edge_weights = [data.get('weight', 1) for _, _, data in G.edges(data=True)]
        print(f"边权重范围: {min(edge_weights)} - {max(edge_weights)}")

    def _plot_network_metrics_comparison(self):
        """绘制网络指标对比图 - 修复版本"""
        if 'network_metrics' not in self.analysis_results:
            print("没有网络指标数据，跳过指标对比图")
            return

        metrics_data = self.analysis_results['network_metrics']

        # 过滤掉空网络
        valid_networks = {name: metrics for name, metrics in metrics_data.items()
                          if metrics.get('number_of_nodes', 0) > 0}

        if not valid_networks:
            print("没有有效的网络指标数据")
            return

        # 创建图形
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        axes = axes.flatten()

        # 准备数据
        network_names = list(valid_networks.keys())
        node_counts = [valid_networks[name].get('number_of_nodes', 0) for name in network_names]
        edge_counts = [valid_networks[name].get('number_of_edges', 0) for name in network_names]
        densities = [valid_networks[name].get('density', 0) for name in network_names]
        avg_degrees = [valid_networks[name].get('average_degree', 0) for name in network_names]

        # 1. 节点和边数量
        x = range(len(network_names))
        width = 0.35
        axes[0].bar([i - width / 2 for i in x], node_counts, width, label='节点数', alpha=0.7, color='skyblue')
        axes[0].bar([i + width / 2 for i in x], edge_counts, width, label='边数', alpha=0.7, color='lightcoral')
        axes[0].set_xticks(x)  # 先设置ticks
        axes[0].set_xticklabels(network_names, rotation=45, ha='right')  # 再设置labels
        axes[0].set_title('网络规模对比', fontweight='bold')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # 在柱子上添加数值
        for i, (nodes, edges) in enumerate(zip(node_counts, edge_counts)):
            axes[0].text(i - width / 2, nodes + max(node_counts) * 0.01, str(nodes),
                         ha='center', va='bottom', fontsize=8)
            axes[0].text(i + width / 2, edges + max(edge_counts) * 0.01, str(edges),
                         ha='center', va='bottom', fontsize=8)

        # 2. 网络密度
        bars = axes[1].bar(network_names, densities, color='orange', alpha=0.7)
        axes[1].set_xticks(range(len(network_names)))  # 修复：先设置ticks
        axes[1].set_xticklabels(network_names, rotation=45, ha='right')
        axes[1].set_title('网络密度对比', fontweight='bold')
        axes[1].grid(True, alpha=0.3)

        # 添加密度数值
        for bar, density in zip(bars, densities):
            axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(densities) * 0.01,
                         f'{density:.3f}', ha='center', va='bottom', fontsize=8)

        # 3. 平均度
        bars = axes[2].bar(network_names, avg_degrees, color='green', alpha=0.7)
        axes[2].set_xticks(range(len(network_names)))  # 修复：先设置ticks
        axes[2].set_xticklabels(network_names, rotation=45, ha='right')
        axes[2].set_title('平均度对比', fontweight='bold')
        axes[2].grid(True, alpha=0.3)

        # 添加平均度数值
        for bar, avg_degree in zip(bars, avg_degrees):
            axes[2].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(avg_degrees) * 0.01,
                         f'{avg_degree:.1f}', ha='center', va='bottom', fontsize=8)

        # 4. 连通分量或其他指标
        if any('connected_components' in valid_networks[name] for name in network_names):
            components = [valid_networks[name].get('connected_components', 1) for name in network_names]
            bars = axes[3].bar(network_names, components, color='purple', alpha=0.7)
            axes[3].set_xticks(range(len(network_names)))  # 修复：先设置ticks
            axes[3].set_xticklabels(network_names, rotation=45, ha='right')
            axes[3].set_title('连通分量数量', fontweight='bold')
            axes[3].grid(True, alpha=0.3)

            # 添加连通分量数值
            for bar, comp in zip(bars, components):
                axes[3].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(components) * 0.01,
                             str(comp), ha='center', va='bottom', fontsize=8)
        else:
            # 如果没有连通分量数据，显示聚类系数
            if any('clustering_coefficient' in valid_networks[name] for name in network_names):
                clustering = [valid_networks[name].get('clustering_coefficient', 0) for name in network_names]
                bars = axes[3].bar(network_names, clustering, color='purple', alpha=0.7)
                axes[3].set_xticks(range(len(network_names)))  # 修复：先设置ticks
                axes[3].set_xticklabels(network_names, rotation=45, ha='right')
                axes[3].set_title('聚类系数对比', fontweight='bold')
                axes[3].grid(True, alpha=0.3)

                # 添加聚类系数数值
                for bar, cluster in zip(bars, clustering):
                    axes[3].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(clustering) * 0.01,
                                 f'{cluster:.3f}', ha='center', va='bottom', fontsize=8)
            else:
                axes[3].axis('off')
                axes[3].text(0.5, 0.5, '无其他指标数据', ha='center', va='center',
                             transform=axes[3].transAxes, fontsize=12)

        plt.tight_layout()
        filename = os.path.join(self.visualizer.output_dir, "network_metrics_comparison.png")
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"网络指标对比图已保存: {filename}")
        plt.show()

        return fig

    # 在 main_analysis.py 中添加超网分析
    def run_hyper_network_analysis(self):
        """运行超网分析"""
        print("\n" + "=" * 60)
        print("开始超网分析")
        print("=" * 60)

        try:
            from hyper.hyper_network_builder import CombatHyperNetworkBuilder
            from hyper.hyper_network_analyzer import HyperNetworkAnalyzer

            # 1. 构建超网
            print("1. 构建超网结构...")
            hyper_builder = CombatHyperNetworkBuilder()
            hyper_data = hyper_builder.build_hyper_network(self.processor)

            # 2. 超网分析
            print("2. 超网特性分析...")
            hyper_analyzer = HyperNetworkAnalyzer()
            hyper_analysis = hyper_analyzer.analyze_hyper_network(hyper_data)

            # 3. 集成结果
            self.analysis_results['hyper_network'] = {
                'data': hyper_data,
                'analysis': hyper_analysis
            }

            # 4. 生成超网报告
            self._generate_hyper_network_report(hyper_data, hyper_analysis)
            from hyper.hyper_network_visualizer import HyperNetworkVisualizer

            #5. 创建可视化器
            visualizer = HyperNetworkVisualizer(figsize=(16, 12))

            # 可视化整个超网络
            visualizer.visualize_hyper_network(hyper_data,
                                               save_path='./outputs/hyper.png')

            print("超网分析完成!")
            return hyper_analysis

        except Exception as e:
            print(f"超网分析失败: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def run_dynamic_hyper_analysis(self, window_size=120, step=30):
        """
        执行动态超网演化分析（增量模式）
        """
        import os
        # 确保从正确的路径导入
        from hyper.hyper_network_visualizer import HyperNetworkVisualizer
        from hyper.hyper_network_builder import CombatHyperNetworkBuilder

        print("\n" + "=" * 60)
        print(f"开始增量动态分析 (窗口:{window_size}s, 步长:{step}s)")
        print("=" * 60)

        # 1. 获取所有时间窗口
        windows = self.processor.get_time_windows(window_size, step)
        output_dir = "./outputs/dynamic_frames"
        os.makedirs(output_dir, exist_ok=True)

        # 【关键修改】：在循环外部初始化，以保持坐标缓存和网络状态累积
        # 增加 figsize 确保 3D 视野足够大
        visualizer = HyperNetworkVisualizer(figsize=(12, 12))
        builder = CombatHyperNetworkBuilder()

        frame_files = []
        # for i, (start, end, df_subset) in enumerate(windows):
        #     print(f"正在处理帧 {i + 1}/{len(windows)}: {start}s - {end}s")
        #
        #     # 【核心逻辑】：使用同一个 builder 实例进行增量构建
        #     # 确保 build_hyper_network_from_subset 内部不重置 self.hyper_network
        #     hyper_data = builder.build_hyper_network_from_subset(self.processor, df_subset)
        #
        #     # 检查当前是否有节点
        #     if hyper_data['hyper_network'].number_of_nodes() == 0:
        #         print(f"警告：时间段 {start}-{end}s 内无有效交互数据")
        #         continue
        #
        #     # 保存为图片
        #     save_path = os.path.join(output_dir, f"frame_{i:03d}.png")
        #
        #     # 【核心逻辑】：使用同一个 visualizer 实例，确保节点 (x, y) 坐标被缓存不跳动
        #     visualizer.visualize_hyper_network(hyper_data, save_path=save_path, azim=35 + i)
        #     frame_files.append(save_path)
        for i, (start, end, df_subset) in enumerate(windows):
            print(f"正在处理帧 {i + 1}/{len(windows)}: {start}s - {end}s")

            # 1. 增量构建超网
            hyper_data = builder.build_hyper_network_from_subset(self.processor, df_subset)
            current_net = hyper_data['hyper_network']

            if current_net.number_of_nodes() == 0:
                continue


            # 因为 GravityCenterAnalyzer 需要简单有向图，我们做一个转换
            temp_graph = nx.DiGraph(current_net)
            gravity_results = self.gravity_analyzer.analyze_network_gravity(temp_graph)

            # 提取重心节点 ID (composite_centrality 最高的节点)
            current_gravity_node = gravity_results.get('basic_gravity', {}).get('gravity_node')


            save_path = os.path.join(output_dir, f"frame_{i:03d}.png")

            # 2. 传入 gravity_node 进行可视化
            visualizer.visualize_hyper_network(
                hyper_data,
                save_path=save_path,
                azim=35 + i,
                gravity_node=current_gravity_node
            )

            frame_files.append(save_path)

        print(f"\n动态帧已生成并保存至: {output_dir}")
        print(f"当前超网最终规模: {builder.hyper_network.number_of_nodes()} 节点")
        return frame_files


    def _generate_hyper_network_report(self, hyper_data: Dict, hyper_analysis: Dict):
        """生成超网分析报告"""
        report_content = "# 作战超网分析报告\n\n"

        # 超网结构信息
        report_content += "## 超网结构概览\n\n"
        report_content += f"- 网络层数: {len(hyper_data['layers'])}\n"
        report_content += f"- 跨层连接数: {len(hyper_data['cross_layer_edges'])}\n"
        report_content += f"- 跨层连接密度: {hyper_data['metrics']['cross_layer_density']:.3f}\n"
        report_content += f"- 层间耦合强度: {hyper_data['metrics']['layer_coupling_strength']:.3f}\n\n"

        # 跨层关键节点
        if 'cross_layer_centrality' in hyper_analysis:
            report_content += "## 跨层关键节点\n\n"
            top_nodes = list(hyper_analysis['cross_layer_centrality'].items())[:10]
            for i, (node, score) in enumerate(top_nodes, 1):
                report_content += f"{i}. {node}: {score:.3f}\n"
            report_content += "\n"

        # 层间影响力
        if 'layer_influence' in hyper_analysis:
            report_content += "## 层间影响力分析\n\n"
            for layer, influence in hyper_analysis['layer_influence'].items():
                report_content += f"- {layer}层: {influence:.3f}\n"
            report_content += "\n"

        # 保存报告
        filename = "outputs/reports/hyper_network_analysis.md"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"超网分析报告已生成: {filename}")

        # 修改 src/main_analysis.py 中的方法


# 使用示例
# if __name__ == "__main__":
#     # 修改为你的数据路径
#     data_path = "../data/raw/111.csv"
#
#     # 运行分析
#     analyzer = MainAnalysis(data_path)
#     results = analyzer.run_comprehensive_analysis()
#
#     # 输出关键发现
#     findings = analyzer.get_key_findings()
#     print("\n关键发现:")
#     print("-" * 40)
#     if 'top_critical_nodes' in findings:
#         print("关键节点:")
#         for node_info in findings['top_critical_nodes']:
#             print(f"  {node_info['node']}: {node_info['score']:.3f}")
#
#     if 'gravity_center' in findings:
#         gc = findings['gravity_center']
#         print(f"网络重心: {gc['node']} (分数: {gc['score']:.3f}, 稳定性: {gc['stability']})")

if __name__ == "__main__":
    # 1. 初始化
    data_path = "../data/raw/111.csv"
    analyzer = MainAnalysis(data_path)
    analyzer.processor = AFSIMDataProcessor(data_path)

    # 2. 生成动态帧
    print("正在生成 3D 动态帧...")
    frames = analyzer.run_dynamic_hyper_analysis(window_size=120, step=30)

    # 3. 合成视频 (使用 imageio.v3 避免 backend 错误)
    if frames:
        try:
            import imageio.v3 as iio
            import os

            print(f"🎬 正在读取 {len(frames)} 个帧...")
            images = []
            for f in frames:
                if os.path.exists(f):
                    # 使用 v3 接口读取，避免 imread 警告
                    img = iio.imread(f)
                    images.append(img)

            if images:
                output_file = './outputs/hyper_evolution_3d.mp4'
                # 设置 fps=5 让演化更流畅
                iio.imwrite(output_file, images, fps=5, codec='libx264')
                print(f"✅ 视频已生成: {output_file}")
        except Exception as e:
            print(f"❌ 合成失败: {e}")