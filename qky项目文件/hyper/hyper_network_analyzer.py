# src/hyper_network_analyzer.py
import sys
import os
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from collections import defaultdict  # 添加这行

# 将项目根目录加入 sys.path，确保能导入 shapely_gravity_analyzer 和 cascade_failure_simulator
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_THIS_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from shapely_gravity_analyzer import ShapelyGravityAnalyzer
from cascade_failure_simulator import CascadeFailureSimulator


class HyperNetworkAnalyzer:
    def __init__(self, shapley_samples: int = 200, cascade_rounds: int = 30):
        """
        :param shapley_samples: Shapley 值蒙特卡洛采样次数
        :param cascade_rounds:  级联失效 Monte Carlo 轮数
        """
        self.shapley_analyzer = ShapelyGravityAnalyzer(n_samples=shapley_samples)
        self.cascade_simulator = CascadeFailureSimulator(n_rounds=cascade_rounds)

    def analyze_hyper_network(self, hyper_network_data: Dict[str, Any],
                               degree_weight: float = 0.4,
                               shapley_weight: float = 0.6,
                               shapley_base_weight: float = 0.7,
                               bridge_bonus_weight: float = 0.3,
                               top_n: int = 10) -> Dict[str, Any]:
        """分析超网结构（含 Shapley 重心分析 + 级联失效模拟）

        :param top_n: Shapley 排名展示前 N 个节点（0 = 全部）
        """
        print("开始超网分析...")

        analysis_results = {}

        # 1. 跨层中心性分析
        analysis_results['cross_layer_centrality'] = self._calculate_cross_layer_centrality(hyper_network_data)

        # 2. 层间影响分析
        analysis_results['layer_influence'] = self._analyze_layer_influence(hyper_network_data)

        # 3. 超网鲁棒性分析
        analysis_results['hyper_robustness'] = self._analyze_hyper_robustness(hyper_network_data)

        # 4. 跨层信息流分析
        analysis_results['cross_layer_flow'] = self._analyze_cross_layer_flow(hyper_network_data)

        # 5. Shapley 值重心分析（新增）
        print("\n5. Shapley 值重心分析...")
        try:
            shapley_results = self.shapley_analyzer.analyze_hyper_network(
                hyper_network_data,
                degree_weight=degree_weight,
                shapley_weight=shapley_weight,
                shapley_base_weight=shapley_base_weight,
                bridge_bonus_weight=bridge_bonus_weight,
                top_n=top_n,
            )
            analysis_results['shapley_gravity'] = shapley_results
            gravity = shapley_results.get('gravity_analysis', {})
            print(f"   超网重心节点（Shapley）: {gravity.get('gravity_node', 'N/A')} "
                  f"(分数={gravity.get('gravity_score', 0):.4f}, "
                  f"稳定性={gravity.get('stability', 'N/A')})")
        except Exception as e:
            print(f"   Shapley 分析失败: {e}")
            import traceback; traceback.print_exc()
            analysis_results['shapley_gravity'] = {}

        # 6. 级联失效模拟（新增）
        print("\n6. 级联失效模拟（关键前10节点随机移除）...")
        try:
            # 综合关键节点列表：优先用 Shapley 排名，回退到跨层中心性
            shapley_gravity = analysis_results.get('shapley_gravity', {})
            combined_sv = shapley_gravity.get('combined_shapley', {})
            cross_centrality = analysis_results.get('cross_layer_centrality', {})

            if combined_sv:
                critical_nodes = [n for n, _ in sorted(combined_sv.items(), key=lambda x: x[1], reverse=True)]
            else:
                critical_nodes = list(cross_centrality.keys())

            cascade_result = self.cascade_simulator.simulate_hyper_network(
                hyper_network_data, critical_nodes, top_k=10
            )
            analysis_results['cascade_failure'] = cascade_result

            # 生成 Markdown 报告
            md_report = self.cascade_simulator.generate_markdown_report(
                cascade_result,
                shapley_results=shapley_gravity,
                network_name="作战超网"
            )
            analysis_results['cascade_report_md'] = md_report

            # 保存报告到文件
            report_path = os.path.join(_ROOT_DIR, 'outputs', 'reports', 'cascade_failure_report.md')
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(md_report)
            print(f"   级联失效报告已保存: {report_path}")

        except Exception as e:
            print(f"   级联失效模拟失败: {e}")
            import traceback; traceback.print_exc()
            analysis_results['cascade_failure'] = {}
            analysis_results['cascade_report_md'] = ""

        return analysis_results

    def _calculate_cross_layer_centrality(self, hyper_data: Dict[str, Any]) -> Dict[str, float]:
        """计算跨层中心性"""
        centrality_scores = {}

        # 收集所有节点
        all_nodes = set()
        for layer_name, layer_net in hyper_data['layers'].items():
            all_nodes.update(layer_net.nodes())

        for node in all_nodes:
            # 1. 层内中心性（加权平均）
            intra_layer_centrality = self._calculate_intra_layer_centrality(node, hyper_data['layers'])

            # 2. 跨层桥梁中心性
            bridge_centrality = self._calculate_bridge_centrality(node, hyper_data['cross_layer_edges'])

            # 3. 信息流控制中心性
            flow_control_centrality = self._calculate_flow_control_centrality(node, hyper_data)

            # 综合跨层中心性
            cross_layer_score = (intra_layer_centrality * 0.4 +
                                 bridge_centrality * 0.3 +
                                 flow_control_centrality * 0.3)

            centrality_scores[node] = cross_layer_score

        return dict(sorted(centrality_scores.items(), key=lambda x: x[1], reverse=True))

    def _calculate_intra_layer_centrality(self, node: str, layers: Dict[str, nx.Graph]) -> float:
        """计算节点在各层内的中心性"""
        scores = []
        for layer_name, layer_net in layers.items():
            if node in layer_net.nodes():
                # 计算该节点在该层的度中心性
                if layer_net.number_of_nodes() > 0:
                    degree = layer_net.degree(node)
                    max_degree = max(dict(layer_net.degree()).values())
                    layer_score = degree / max_degree if max_degree > 0 else 0
                    scores.append(layer_score)

        return np.mean(scores) if scores else 0.0

    def _calculate_bridge_centrality(self, node: str, cross_edges: List[Dict]) -> float:
        """计算跨层桥梁中心性"""
        # 统计该节点参与的跨层连接数量
        node_cross_edges = 0
        for edge in cross_edges:
            if (edge['source_node'] == node and edge['source_layer'] != edge['target_layer']) or \
                    (edge['target_node'] == node and edge['source_layer'] != edge['target_layer']):
                node_cross_edges += 1

        total_cross_edges = len(cross_edges)
        return node_cross_edges / total_cross_edges if total_cross_edges > 0 else 0.0

    def _calculate_flow_control_centrality(self, node: str, hyper_data: Dict[str, Any]) -> float:
        """计算信息流控制中心性"""
        # 简化的信息流控制计算
        # 在实际应用中，这需要复杂的信息流模拟

        flow_control = 0.0
        layers = hyper_data['layers']
        cross_edges = hyper_data['cross_layer_edges']

        # 检查节点是否在关键的信息流路径上
        for edge in cross_edges:
            if edge['source_node'] == node or edge['target_node'] == node:
                flow_control += edge['weight']

        max_possible_flow = sum(edge['weight'] for edge in cross_edges)
        return flow_control / max_possible_flow if max_possible_flow > 0 else 0.0

    def _analyze_layer_influence(self, hyper_data: Dict[str, Any]) -> Dict[str, float]:
        """分析层间影响力"""
        layer_influence = {}
        cross_edges = hyper_data['cross_layer_edges']

        # 统计各层作为源层和目标层的次数
        source_count = defaultdict(int)
        target_count = defaultdict(int)

        for edge in cross_edges:
            source_count[edge['source_layer']] += 1
            target_count[edge['target_layer']] += 1

        total_edges = len(cross_edges)
        for layer in hyper_data['layers'].keys():
            influence = (source_count[layer] - target_count[layer]) / total_edges if total_edges > 0 else 0
            layer_influence[layer] = influence

        return layer_influence

    def _analyze_hyper_robustness(self, hyper_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析超网鲁棒性"""
        robustness = {}

        # 模拟跨层节点失效的影响
        top_nodes = list(self._calculate_cross_layer_centrality(hyper_data).keys())[:3]

        removal_impact = {}
        for node in top_nodes:
            impact = self._simulate_cross_layer_removal(node, hyper_data)
            removal_impact[node] = impact

        robustness['cross_layer_removal_impact'] = removal_impact
        robustness['layer_interdependence'] = self._calculate_layer_interdependence(hyper_data)

        return robustness

    def _simulate_cross_layer_removal(self, node: str, hyper_data: Dict[str, Any]) -> Dict[str, float]:
        """模拟跨层节点移除的影响"""
        # 简化的跨层移除影响计算
        impact = {
            'layers_affected': 0,
            'cross_edges_lost': 0,
            'connectivity_loss': 0.0
        }

        # 计算影响的层数
        layers_affected = 0
        for layer_name, layer_net in hyper_data['layers'].items():
            if node in layer_net.nodes():
                layers_affected += 1

        # 计算丢失的跨层连接
        cross_edges_lost = 0
        for edge in hyper_data['cross_layer_edges']:
            if edge['source_node'] == node or edge['target_node'] == node:
                cross_edges_lost += 1

        impact['layers_affected'] = layers_affected
        impact['cross_edges_lost'] = cross_edges_lost
        impact['connectivity_loss'] = cross_edges_lost / len(hyper_data['cross_layer_edges']) if hyper_data[
            'cross_layer_edges'] else 0

        return impact

    def _calculate_layer_interdependence(self, hyper_data: Dict[str, Any]) -> float:
        """计算层间依赖程度"""
        cross_edges = hyper_data['cross_layer_edges']
        total_intra_edges = sum(layer_net.number_of_edges() for layer_net in hyper_data['layers'].values())

        total_edges = total_intra_edges + len(cross_edges)
        return len(cross_edges) / total_edges if total_edges > 0 else 0.0

    def _analyze_cross_layer_flow(self, hyper_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析跨层信息流"""
        flow_analysis = {}

        # 统计不同类型的信息流
        flow_types = defaultdict(int)
        for edge in hyper_data['cross_layer_edges']:
            flow_type = f"{edge['source_layer']}_to_{edge['target_layer']}"
            flow_types[flow_type] += 1

        flow_analysis['flow_type_distribution'] = dict(flow_types)
        flow_analysis['dominant_flow'] = max(flow_types.items(), key=lambda x: x[1]) if flow_types else ('none', 0)

        return flow_analysis