# src/hyper_network_builder.py
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from collections import defaultdict


class CombatHyperNetworkBuilder:
    def __init__(self):
        self.layers = {}  # 存储各层网络
        self.cross_layer_edges = []  # 显式存储跨层连接
        self.hyper_network = nx.MultiDiGraph()  # 超网主体

        # src/hyper/hyper_network_builder.py

    def build_hyper_network(self, processor) -> Dict[str, Any]:
        """
        核心逻辑：构建作战超网。
        实现节点持久化（不清除节点），但连边动态化（每帧清除旧边）。
        """
        self.layers = {}
        self.cross_layer_edges = []

        # 【核心修改点】：每帧只清除边，不清除节点。
        # 这样 self.hyper_network 会累积所有出现过的节点，实现位置固定和持久化。
        self.hyper_network.remove_edges_from(list(self.hyper_network.edges()))

        # 1. 构建各层临时网络（当前时间窗口内的数据）
        self._build_all_layers(processor)

        # 2. 建立显式跨层连接
        self._build_cross_layer_connections(processor)

        # 3. 增强版节点合并逻辑
        for layer_name, layer_net in self.layers.items():
            for node in layer_net.nodes():
                # 无论节点是否已存在，都尝试通过分类器获取其“天生身份”
                # 这样可以防止指挥节点被锁死在传感器层
                identity = self._classify_node(node)

                # 确定该节点的物理显示层
                # 如果是 unknown 或 target，则留在发现它的那一层
                display_layer = identity if identity in ['sensor', 'command', 'weapon', 'ew'] else layer_name

                if node not in self.hyper_network:
                    self.hyper_network.add_node(node, layer=display_layer)
                else:
                    # 如果节点已存在但层级不对（比如之前是sensor现在发现是command），进行修正
                    current_layer = self.hyper_network.nodes[node].get('layer')
                    if current_layer == 'sensor' and display_layer == 'command':
                        self.hyper_network.nodes[node]['layer'] = 'command'

            for u, v, data in layer_net.edges(data=True):
                self.hyper_network.add_edge(u, v, **data, type='intra')

        # 4. 处理跨层连接的持久化与连边
        for edge in self.cross_layer_edges:
            u, v = edge['source_node'], edge['target_node']
            # 确保跨层连接的两个端点都已在图中持久化
            for n, l in [(u, edge['source_layer']), (v, edge['target_layer'])]:
                if n not in self.hyper_network:
                    actual_type = self._classify_node(n)
                    display_layer = actual_type if actual_type in ['sensor', 'command', 'weapon', 'ew'] else l
                    self.hyper_network.add_node(n, layer=display_layer)

            # 添加当前窗口的跨层边
            self.hyper_network.add_edge(u, v, weight=edge['weight'], type='inter')

        # 5. 计算指标
        hyper_metrics = self._calculate_hyper_metrics()

        return {
            'layers': self.layers,
            'cross_layer_edges': self.cross_layer_edges,
            'hyper_network': self.hyper_network,
            'metrics': hyper_metrics
        }


    def build_hyper_network_from_subset(self, processor, df_subset: pd.DataFrame) -> Dict[str, Any]:
        """使用特定的数据子集构建超网快照"""
        # 临时保存原始数据
        original_df = processor.df
        # 注入时间切片数据
        processor.df = df_subset

        # 调用原有的构建逻辑
        result = self.build_hyper_network(processor)

        # 还原原始数据
        processor.df = original_df
        return result


    def _build_all_layers(self, processor):
        """构建所有网络层"""
        # 传感器层
        self.layers['sensor'] = self._build_sensor_layer(processor)

        # 指挥控制层
        self.layers['command'] = self._build_command_layer(processor)

        # 武器打击层
        self.layers['weapon'] = self._build_weapon_layer(processor)

        # 电子战层
        self.layers['ew'] = self._build_ew_layer(processor)

        print("各网络层构建完成:")
        for layer_name, network in self.layers.items():
            print(f"  {layer_name}: {network.number_of_nodes()}节点, {network.number_of_edges()}边")

    def _build_sensor_layer(self, processor) -> nx.DiGraph:
        """构建传感器层"""
        G = nx.DiGraph()
        # 从MsgSensorDetectionChange提取探测关系
        detection_data = processor.df[processor.df['type（信息类型）'] == 'MsgSensorDetectionChange']

        for _, row in detection_data.iterrows():
            sensor = row['platform（所有者或源平台）']
            target = row['interactor']
            if pd.notna(sensor) and pd.notna(target) and row.get('8') == 'TRUE':
                G.add_edge(sensor, target,
                           relation='detects',
                           layer='sensor',
                           weight=1.0)

        return G

    def _build_command_layer(self, processor) -> nx.DiGraph:
        """构建指挥控制层"""
        G = nx.DiGraph()
        # 从MsgTaskUpdate提取指挥关系
        task_data = processor.df[processor.df['type（信息类型）'] == 'MsgTaskUpdate']

        for _, row in task_data.iterrows():
            commander = row['platform（所有者或源平台）']
            subordinate = row['interactor']
            if pd.notna(commander) and pd.notna(subordinate):
                G.add_edge(commander, subordinate,
                           relation='commands',
                           layer='command',
                           weight=1.0)

        return G

    def _build_weapon_layer(self, processor) -> nx.DiGraph:
        """构建武器打击层"""
        G = nx.DiGraph()
        # 从MsgWeaponFired提取打击关系
        weapon_data = processor.df[processor.df['type（信息类型）'] == 'MsgWeaponFired']

        for _, row in weapon_data.iterrows():
            launcher = row['platform（所有者或源平台）']
            target = row['interactor']
            if pd.notna(launcher) and pd.notna(target):
                G.add_edge(launcher, target,
                           relation='engages',
                           layer='weapon',
                           weight=1.0)

        return G

    def _build_ew_layer(self, processor) -> nx.DiGraph:
        """构建电子战层"""
        G = nx.DiGraph()
        # 从MsgJammingRequestInitiated提取干扰关系
        jamming_data = processor.df[processor.df['type（信息类型）'] == 'MsgJammingRequestInitiated']

        for _, row in jamming_data.iterrows():
            jammer = row['platform（所有者或源平台）']
            target = row['interactor']
            if pd.notna(jammer) and pd.notna(target):
                G.add_edge(jammer, target,
                           relation='jams',
                           layer='ew',
                           weight=1.0)

        return G

    def _build_cross_layer_connections(self, processor):
        """建立显式跨层连接 - 超网核心"""
        print("建立跨层连接...")

        # 1. 探测→指挥连接（传感器发现目标触发指挥决策）
        self._connect_sensor_to_command()

        # 2. 指挥→打击连接（指挥命令触发武器打击）
        self._connect_command_to_weapon()

        # 3. 电子战→传感器连接（干扰影响探测）
        self._connect_ew_to_sensor()

        # 4. 跨层协同连接
        self._connect_cross_layer_coordination()

        print(f"建立 {len(self.cross_layer_edges)} 个跨层连接")

    def _connect_sensor_to_command(self):
        """传感器层→指挥层连接"""
        for sensor_node in self.layers['sensor'].nodes():
            for command_node in self.layers['command'].nodes():
                # 如果传感器和指挥节点属于同一系统
                if self._belong_to_same_system(sensor_node, command_node):
                    self.cross_layer_edges.append({
                        'source_node': sensor_node,
                        'source_layer': 'sensor',
                        'target_node': command_node,
                        'target_layer': 'command',
                        'relation': 'reports_to',
                        'weight': 0.8
                    })

    def _connect_command_to_weapon(self):
        """指挥层→武器层连接"""
        for command_node in self.layers['command'].nodes():
            for weapon_node in self.layers['weapon'].nodes():
                if self._belong_to_same_system(command_node, weapon_node):
                    self.cross_layer_edges.append({
                        'source_node': command_node,
                        'source_layer': 'command',
                        'target_node': weapon_node,
                        'target_layer': 'weapon',
                        'relation': 'controls',
                        'weight': 0.9
                    })

    def _connect_ew_to_sensor(self):
        """电子战层→传感器层连接"""
        for ew_node in self.layers['ew'].nodes():
            for sensor_node in self.layers['sensor'].nodes():
                # 电子战平台可以干扰敌方传感器
                if self._is_adversarial(ew_node, sensor_node):
                    self.cross_layer_edges.append({
                        'source_node': ew_node,
                        'source_layer': 'ew',
                        'target_node': sensor_node,
                        'target_layer': 'sensor',
                        'relation': 'degrades',
                        'weight': 0.7
                    })

    def _connect_cross_layer_coordination(self):
        """跨层协同连接"""
        # 同一平台在不同层中的自我连接
        all_nodes = set()
        for layer in self.layers.values():
            all_nodes.update(layer.nodes())

        for node in all_nodes:
            # 找到该节点在哪些层中存在
            node_layers = []
            for layer_name, layer_net in self.layers.items():
                if node in layer_net.nodes():
                    node_layers.append(layer_name)

            # 为同一节点在不同层之间建立连接
            for i in range(len(node_layers)):
                for j in range(i + 1, len(node_layers)):
                    self.cross_layer_edges.append({
                        'source_node': node,
                        'source_layer': node_layers[i],
                        'target_node': node,
                        'target_layer': node_layers[j],
                        'relation': 'same_entity',
                        'weight': 1.0
                    })

    def _belong_to_same_system(self, node1: str, node2: str) -> bool:
        """判断两个节点是否属于同一作战系统"""
        # 简化的判断逻辑，实际应根据平台编号等规则
        if 'iads' in node1.lower() and 'iads' in node2.lower():
            return True
        if 'sam' in node1.lower() and 'sam' in node2.lower():
            return True
        if node1.split('_')[0] == node2.split('_')[0]:  # 相同编号前缀
            return True
        return False

    def _is_adversarial(self, node1: str, node2: str) -> bool:
        """判断两个节点是否为对抗关系"""
        # 简化的对抗关系判断
        friendly_keywords = ['iads', 'sam', 'cmdr']
        adversarial_keywords = ['target', 'ucav', 'soj']

        node1_type = self._classify_node(node1)
        node2_type = self._classify_node(node2)

        return (node1_type in friendly_keywords and node2_type in adversarial_keywords) or \
               (node1_type in adversarial_keywords and node2_type in friendly_keywords)

    def _classify_node(self, node: str) -> str:
        """分类节点类型"""
        node_lower = node.lower()
        if any(kw in node_lower for kw in ['iads', 'cmdr', 'command']):
            return 'command'
        elif any(kw in node_lower for kw in ['radar', 'sensor']):
            return 'sensor'
        elif any(kw in node_lower for kw in ['sam', 'launcher', 'weapon']):
            return 'weapon'
        elif any(kw in node_lower for kw in ['soj', 'jammer', 'ew']):
            return 'ew'
        elif any(kw in node_lower for kw in ['target', 'ucav']):
            return 'target'
        else:
            return 'unknown'

    def _calculate_hyper_metrics(self) -> Dict[str, float]:
        """计算超网特有指标"""
        metrics = {}

        # 1. 跨层连接密度
        total_possible_cross_edges = self._calculate_possible_cross_edges()
        metrics['cross_layer_density'] = len(
            self.cross_layer_edges) / total_possible_cross_edges if total_possible_cross_edges > 0 else 0

        # 2. 层间耦合强度
        metrics['layer_coupling_strength'] = self._calculate_coupling_strength()

        # 3. 跨层连通性
        metrics['cross_layer_connectivity'] = self._calculate_cross_layer_connectivity()

        return metrics

    def _calculate_possible_cross_edges(self) -> int:
        """计算可能的跨层连接总数"""
        total = 0
        layer_names = list(self.layers.keys())
        for i in range(len(layer_names)):
            for j in range(len(layer_names)):
                if i != j:
                    layer1_nodes = len(self.layers[layer_names[i]].nodes())
                    layer2_nodes = len(self.layers[layer_names[j]].nodes())
                    total += layer1_nodes * layer2_nodes
        return total

    def _calculate_coupling_strength(self) -> float:
        """计算层间耦合强度"""
        if not self.cross_layer_edges:
            return 0.0

        total_weight = sum(edge['weight'] for edge in self.cross_layer_edges)
        return total_weight / len(self.cross_layer_edges)

    def _calculate_cross_layer_connectivity(self) -> float:
        """计算跨层连通性"""
        # 计算有多少节点参与了跨层连接
        cross_layer_nodes = set()
        for edge in self.cross_layer_edges:
            cross_layer_nodes.add((edge['source_node'], edge['source_layer']))
            cross_layer_nodes.add((edge['target_node'], edge['target_layer']))

        total_nodes = sum(len(layer.nodes()) for layer in self.layers.values())
        return len(cross_layer_nodes) / total_nodes if total_nodes > 0 else 0