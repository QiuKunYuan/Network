# src/network_builder.py
import networkx as nx
import pandas as pd
from typing import Dict, List, Tuple
from collections import defaultdict


class CombatNetworkBuilder:
    def __init__(self):
        self.networks = {}

    def build_multi_layer_network(self, processor) -> Dict[str, nx.Graph]:
        """构建多层作战网络"""
        print("开始构建多层作战网络...")

        networks = {}

        try:
            # 1. 通信网络
            print("构建通信网络...")
            networks['communication'] = self._build_communication_network(processor)

            # 2. 传感器网络
            print("构建传感器网络...")
            networks['sensor'] = self._build_sensor_network(processor)

            # 3. 指挥网络
            print("构建指挥网络...")
            networks['command'] = self._build_command_network(processor)

            # 4. 综合网络
            print("构建综合网络...")
            networks['integrated'] = self._build_integrated_network(networks)

            print("网络构建完成!")
            for name, net in networks.items():
                print(f"  {name}: {net.number_of_nodes()}节点, {net.number_of_edges()}边")

        except Exception as e:
            print(f"网络构建错误: {e}")
            # 如果某个网络构建失败，继续构建其他网络
            pass

        return networks

    def _build_communication_network(self, processor) -> nx.Graph:
        """构建通信网络"""
        G = nx.Graph()

        try:
            links = processor.extract_communication_links()
            for source, target, weight in links:
                G.add_edge(source, target, weight=weight, layer='communication', relation='communicates')
        except Exception as e:
            print(f"通信网络构建失败: {e}")

        return G

    def _build_sensor_network(self, processor) -> nx.DiGraph:
        """构建传感器网络"""
        G = nx.DiGraph()

        try:
            detections = processor.extract_sensor_detections()
            for sensor, target, weight in detections:
                G.add_edge(sensor, target, weight=weight, layer='sensor', relation='detects')
        except Exception as e:
            print(f"传感器网络构建失败: {e}")

        return G

    def _build_command_network(self, processor) -> nx.DiGraph:
        """构建指挥网络"""
        G = nx.DiGraph()

        try:
            hierarchy = processor.extract_platform_hierarchy()
            for subordinate, commander in hierarchy.items():
                G.add_edge(commander, subordinate, weight=1.0, layer='command', relation='commands')
        except Exception as e:
            print(f"指挥网络构建失败: {e}")

        return G

    # 改进的 _build_integrated_network 方法
    def _build_integrated_network(self, networks: Dict) -> nx.Graph:
        """构建综合网络 - 改进版本"""
        G = nx.Graph()

        # 定义不同网络层的权重
        layer_weights = {
            'sensor_detection': 1.0,  # 传感器探测 - 重要
            'task_assignment': 0.8,  # 任务分配 - 重要
            'electronic_warfare': 0.7,  # 电子战 - 中等
            'weapon_system': 0.6,  # 武器系统 - 中等
            'spatiotemporal': 0.3,  # 时空共现 - 较弱
            'functional': 0.2,  # 功能类型 - 最弱
        }

        for layer_name, network in networks.items():
            if layer_name == 'integrated':
                continue

            layer_weight = layer_weights.get(layer_name, 0.5)

            for u, v, data in network.edges(data=True):
                edge_weight = data.get('weight', 1.0) * layer_weight

                if G.has_edge(u, v):
                    # 累加权重，但考虑层重要性
                    G[u][v]['weight'] += edge_weight
                    G[u][v]['layers'].append(layer_name)
                else:
                    G.add_edge(u, v, weight=edge_weight, layers=[layer_name])

        return G

    def _build_spatiotemporal_network(self, df: pd.DataFrame) -> nx.Graph:
        """构建时空共现网络 - 改进版本"""
        G = nx.Graph()

        entity_data = df[df['type（信息类型）'] == 'MsgEntityState']

        # 更严格的时间窗口和共现阈值
        time_windows = entity_data['time（时间）'].unique()
        cooccurrence_count = defaultdict(int)

        for time_window in time_windows[:min(100, len(time_windows))]:  # 限制时间窗口
            platforms_in_window = entity_data[
                entity_data['time（时间）'] == time_window
                ]['platform（所有者或源平台）'].dropna().unique()

            # 只记录真正有意义的共现（小范围）
            for i in range(len(platforms_in_window)):
                for j in range(i + 1, len(platforms_in_window)):
                    # 只记录同一类型平台或指挥-被指挥关系
                    p1_type = self._classify_platform(platforms_in_window[i])
                    p2_type = self._classify_platform(platforms_in_window[j])

                    if self._should_connect_spatially(p1_type, p2_type):
                        pair = tuple(sorted([platforms_in_window[i], platforms_in_window[j]]))
                        cooccurrence_count[pair] += 1

        # 更高的共现阈值
        for (p1, p2), count in cooccurrence_count.items():
            if count >= 5:  # 从2次提高到5次
                weight = min(count / 20.0, 1.0)  # 更严格的归一化
                G.add_edge(p1, p2, weight=weight, cooccurrence_count=count)

        return G

    def _should_connect_spatially(self, type1: str, type2: str) -> bool:
        """判断两种平台类型是否应该在时空网络中连接"""
        # 只连接有明确功能关系的平台
        spatial_connections = {
            'radar': ['command_control', 'sam_system'],
            'sam_system': ['command_control', 'radar'],
            'command_control': ['radar', 'sam_system', 'ew_platform'],
            'ew_platform': ['command_control']
        }

        return type2 in spatial_connections.get(type1, [])