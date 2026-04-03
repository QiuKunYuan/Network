# src/hyper/hyper_network_builder.py
import networkx as nx
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from collections import defaultdict


class CombatHyperNetworkBuilder:
    def __init__(self):
        self.layers = {}
        self.cross_layer_edges = []
        self.hyper_network = nx.MultiDiGraph()

    def build_hyper_network(self, processor) -> Dict[str, Any]:
        """
        核心逻辑：构建作战超网。
        节点持久化（不清除节点），连边动态化（每帧清除旧边）。
        """
        self.layers = {}
        self.cross_layer_edges = []
        self.hyper_network.remove_edges_from(list(self.hyper_network.edges()))

        # 1. 构建各层
        self._build_all_layers(processor)

        # 2. 建立跨层连接
        self._build_cross_layer_connections(processor)

        # 3. 节点合并到超网
        for layer_name, layer_net in self.layers.items():
            for node in layer_net.nodes():
                identity = self._classify_node(node)
                display_layer = identity if identity in ['sensor', 'command', 'weapon', 'ew'] else layer_name

                if node not in self.hyper_network:
                    self.hyper_network.add_node(node, layer=display_layer)
                else:
                    current_layer = self.hyper_network.nodes[node].get('layer')
                    if current_layer == 'sensor' and display_layer == 'command':
                        self.hyper_network.nodes[node]['layer'] = 'command'

            for u, v, data in layer_net.edges(data=True):
                self.hyper_network.add_edge(u, v, **data, type='intra')

        # 4. 跨层连接
        for edge in self.cross_layer_edges:
            u, v = edge['source_node'], edge['target_node']
            for n, l in [(u, edge['source_layer']), (v, edge['target_layer'])]:
                if n not in self.hyper_network:
                    actual_type = self._classify_node(n)
                    display_layer = actual_type if actual_type in ['sensor', 'command', 'weapon', 'ew'] else l
                    self.hyper_network.add_node(n, layer=display_layer)
            self.hyper_network.add_edge(u, v, weight=edge['weight'], type='inter')

        # 5. 兜底：若超网仍为空，从平台层级直接构建
        if self.hyper_network.number_of_nodes() == 0:
            print("  ⚠️ 超网为空，启用兜底构建（从平台层级关系）...")
            self._fallback_build(processor)

        # 6. 计算指标
        hyper_metrics = self._calculate_hyper_metrics()

        print(f"超网构建完成: {self.hyper_network.number_of_nodes()} 节点, "
              f"{self.hyper_network.number_of_edges()} 边")

        return {
            'layers': self.layers,
            'cross_layer_edges': self.cross_layer_edges,
            'hyper_network': self.hyper_network,
            'metrics': hyper_metrics
        }

    def build_hyper_network_from_subset(self, processor, df_subset: pd.DataFrame) -> Dict[str, Any]:
        """使用特定的数据子集构建超网快照"""
        original_df = processor.df
        processor.df = df_subset
        # 同步更新列名缓存
        original_col = processor._col
        from data_processor import _find_col, _COL_ALIASES
        processor._col = {k: _find_col(df_subset, k) for k in _COL_ALIASES}

        result = self.build_hyper_network(processor)

        processor.df = original_df
        processor._col = original_col
        return result

    # ─────────────────────────────────────────────
    # 各层构建
    # ─────────────────────────────────────────────

    def _build_all_layers(self, processor):
        """构建所有网络层"""
        self.layers['sensor'] = self._build_sensor_layer(processor)
        self.layers['command'] = self._build_command_layer(processor)
        self.layers['weapon'] = self._build_weapon_layer(processor)
        self.layers['ew'] = self._build_ew_layer(processor)

        print("各网络层构建完成:")
        for layer_name, network in self.layers.items():
            print(f"  {layer_name}: {network.number_of_nodes()}节点, {network.number_of_edges()}边")

    def _build_sensor_layer(self, processor) -> nx.DiGraph:
        """构建传感器层"""
        G = nx.DiGraph()
        platform_col = processor._col.get('platform')
        interactor_col = processor._col.get('interactor')
        type_col = processor._col.get('type')
        col8 = processor._col.get('col8')

        if not all([platform_col, interactor_col, type_col]):
            return G

        # 方法1：MsgSensorDetectionChange
        detection_data = processor.df[processor.df[type_col] == 'MsgSensorDetectionChange']
        for _, row in detection_data.iterrows():
            sensor = row[platform_col]
            target = row[interactor_col]
            status = str(row.get(col8, 'TRUE')).upper() if col8 else 'TRUE'
            if pd.notna(sensor) and pd.notna(target) and status == 'TRUE':
                G.add_edge(str(sensor), str(target), relation='detects', layer='sensor', weight=1.0)

        # 方法2：从活跃雷达组件推断（兜底）
        if G.number_of_nodes() == 0:
            component_col = processor._col.get('component')
            if component_col:
                sensor_parts = processor.df[
                    (processor.df[type_col] == 'MsgPartStatus') &
                    (processor.df[component_col].isin(['ew_radar', 'acq_radar', 'sensor', 'radar']))
                ]
                if col8:
                    active = sensor_parts[sensor_parts[col8].astype(str).str.upper() == 'TRUE']
                else:
                    active = sensor_parts
                for platform in active[platform_col].dropna().unique():
                    G.add_node(str(platform), layer='sensor')

        return G

    def _build_command_layer(self, processor) -> nx.DiGraph:
        """构建指挥控制层（从层级关系 + MsgTaskUpdate）"""
        G = nx.DiGraph()
        platform_col = processor._col.get('platform')
        interactor_col = processor._col.get('interactor')
        type_col = processor._col.get('type')

        if not all([platform_col, type_col]):
            return G

        # 方法1：MsgTaskUpdate
        if interactor_col:
            task_data = processor.df[processor.df[type_col] == 'MsgTaskUpdate']
            for _, row in task_data.iterrows():
                commander = row[platform_col]
                subordinate = row[interactor_col]
                if pd.notna(commander) and pd.notna(subordinate):
                    G.add_edge(str(commander), str(subordinate),
                               relation='commands', layer='command', weight=1.0)

        # 方法2：从 MsgPlatformInfo 的 default: 层级关系（主要来源）
        hierarchy = processor.extract_platform_hierarchy()
        for subordinate, commander in hierarchy.items():
            G.add_edge(str(commander), str(subordinate),
                       relation='commands', layer='command', weight=0.8)

        # 方法3：若仍为空，把所有 cmdr/iads 节点加入
        if G.number_of_nodes() == 0:
            for platform in processor.get_all_platforms():
                p = str(platform).lower()
                if any(kw in p for kw in ['cmdr', 'iads', 'command']):
                    G.add_node(platform, layer='command')

        return G

    def _build_weapon_layer(self, processor) -> nx.DiGraph:
        """构建武器打击层"""
        G = nx.DiGraph()
        platform_col = processor._col.get('platform')
        interactor_col = processor._col.get('interactor')
        type_col = processor._col.get('type')

        if not all([platform_col, interactor_col, type_col]):
            return G

        weapon_data = processor.df[processor.df[type_col] == 'MsgWeaponFired']
        for _, row in weapon_data.iterrows():
            launcher = row[platform_col]
            target = row[interactor_col]
            if pd.notna(launcher) and pd.notna(target):
                G.add_edge(str(launcher), str(target),
                           relation='engages', layer='weapon', weight=1.0)

        # 兜底：把所有 sam/launcher 节点加入
        if G.number_of_nodes() == 0:
            for platform in processor.get_all_platforms():
                p = str(platform).lower()
                if any(kw in p for kw in ['sam', 'launcher', 'missile', 'weapon']):
                    G.add_node(platform, layer='weapon')

        return G

    def _build_ew_layer(self, processor) -> nx.DiGraph:
        """构建电子战层"""
        G = nx.DiGraph()
        platform_col = processor._col.get('platform')
        interactor_col = processor._col.get('interactor')
        type_col = processor._col.get('type')

        if not all([platform_col, interactor_col, type_col]):
            return G

        jamming_data = processor.df[processor.df[type_col] == 'MsgJammingRequestInitiated']
        for _, row in jamming_data.iterrows():
            jammer = row[platform_col]
            target = row[interactor_col]
            if pd.notna(jammer) and pd.notna(target):
                G.add_edge(str(jammer), str(target),
                           relation='jams', layer='ew', weight=1.0)

        # 兜底：把所有 soj/ew/jammer 节点加入
        if G.number_of_nodes() == 0:
            for platform in processor.get_all_platforms():
                p = str(platform).lower()
                if any(kw in p for kw in ['soj', 'jammer', 'ew_radar', 'ew']):
                    G.add_node(platform, layer='ew')

        return G

    def _fallback_build(self, processor):
        """兜底构建：直接从所有平台和层级关系构建超网"""
        print("  兜底构建：从所有平台节点构建超网...")
        hierarchy = processor.extract_platform_hierarchy()
        all_platforms = processor.get_all_platforms()

        for platform in all_platforms:
            node_type = self._classify_node(platform)
            layer = node_type if node_type in ['sensor', 'command', 'weapon', 'ew'] else 'sensor'
            if platform not in self.hyper_network:
                self.hyper_network.add_node(platform, layer=layer)

        for subordinate, commander in hierarchy.items():
            if subordinate not in self.hyper_network:
                self.hyper_network.add_node(subordinate, layer='command')
            if commander not in self.hyper_network:
                self.hyper_network.add_node(commander, layer='command')
            self.hyper_network.add_edge(commander, subordinate, weight=1.0, type='intra')

        print(f"  兜底构建完成: {self.hyper_network.number_of_nodes()} 节点")

    # ─────────────────────────────────────────────
    # 跨层连接
    # ─────────────────────────────────────────────

    def _build_cross_layer_connections(self, processor):
        """建立显式跨层连接"""
        print("建立跨层连接...")
        self._connect_sensor_to_command()
        self._connect_command_to_weapon()
        self._connect_ew_to_sensor()
        self._connect_cross_layer_coordination()
        print(f"建立 {len(self.cross_layer_edges)} 个跨层连接")

    def _connect_sensor_to_command(self):
        for sensor_node in self.layers['sensor'].nodes():
            for command_node in self.layers['command'].nodes():
                if self._belong_to_same_system(sensor_node, command_node):
                    self.cross_layer_edges.append({
                        'source_node': sensor_node, 'source_layer': 'sensor',
                        'target_node': command_node, 'target_layer': 'command',
                        'relation': 'reports_to', 'weight': 0.8
                    })

    def _connect_command_to_weapon(self):
        for command_node in self.layers['command'].nodes():
            for weapon_node in self.layers['weapon'].nodes():
                if self._belong_to_same_system(command_node, weapon_node):
                    self.cross_layer_edges.append({
                        'source_node': command_node, 'source_layer': 'command',
                        'target_node': weapon_node, 'target_layer': 'weapon',
                        'relation': 'controls', 'weight': 0.9
                    })

    def _connect_ew_to_sensor(self):
        for ew_node in self.layers['ew'].nodes():
            for sensor_node in self.layers['sensor'].nodes():
                if self._is_adversarial(ew_node, sensor_node):
                    self.cross_layer_edges.append({
                        'source_node': ew_node, 'source_layer': 'ew',
                        'target_node': sensor_node, 'target_layer': 'sensor',
                        'relation': 'degrades', 'weight': 0.7
                    })

    def _connect_cross_layer_coordination(self):
        """同一平台在不同层中的自我连接"""
        all_nodes = set()
        for layer in self.layers.values():
            all_nodes.update(layer.nodes())

        for node in all_nodes:
            node_layers = [ln for ln, lnet in self.layers.items() if node in lnet.nodes()]
            for i in range(len(node_layers)):
                for j in range(i + 1, len(node_layers)):
                    self.cross_layer_edges.append({
                        'source_node': node, 'source_layer': node_layers[i],
                        'target_node': node, 'target_layer': node_layers[j],
                        'relation': 'same_entity', 'weight': 1.0
                    })

    # ─────────────────────────────────────────────
    # 辅助方法
    # ─────────────────────────────────────────────

    def _belong_to_same_system(self, node1: str, node2: str) -> bool:
        n1, n2 = str(node1).lower(), str(node2).lower()
        if 'iads' in n1 and 'iads' in n2:
            return True
        if 'sam' in n1 and 'sam' in n2:
            return True
        # 相同数字前缀（如 100_xxx 和 100_yyy）
        p1 = n1.split('_')[0]
        p2 = n2.split('_')[0]
        if p1.isdigit() and p1 == p2:
            return True
        return False

    def _is_adversarial(self, node1: str, node2: str) -> bool:
        t1 = self._classify_node(node1)
        t2 = self._classify_node(node2)
        friendly = {'command', 'sensor', 'weapon'}
        adversarial = {'ew', 'target'}
        return (t1 in adversarial and t2 in friendly) or (t1 in friendly and t2 in adversarial)

    def _classify_node(self, node: str) -> str:
        """
        节点层分类（优先级从高到低）：
          weapon  > command > sensor > ew
        注意：ew_radar / acq_radar 含 'radar' 关键词 → sensor 层
              ucav 是无人作战飞机，作为指挥/协调节点 → command 层
              soj / jammer 才是纯电子战 → ew 层
              'ew' 单独出现才归 ew，避免 ew_radar 误归
        """
        n = str(node).lower()
        # weapon 层：SAM 系统、发射架、导弹、TTR 跟踪雷达
        if any(kw in n for kw in ['sam', 'launcher', 'missile', 'weapon', 'ttr']):
            return 'weapon'
        # command 层：指挥控制、IADS、UCAV（无人机作为指挥节点）
        if any(kw in n for kw in ['iads', 'cmdr', 'command', 'c2', 'c4i', 'ucav']):
            return 'command'
        # sensor 层：所有雷达（含 ew_radar、acq_radar）及传感器
        if any(kw in n for kw in ['radar', 'sensor', 'acq', 'esm']):
            return 'sensor'
        # ew 层：纯电子战压制（SOJ 干扰机、jammer）
        # 注意：只有 _soj / soj_ / 以 soj 结尾 / jammer 才归此层
        if any(kw in n for kw in ['_soj', 'soj_', 'jammer']) or n.endswith('soj') or n == 'soj':
            return 'ew'
        # 兜底 ew 关键词（不含 radar）
        if 'ew' in n and 'radar' not in n:
            return 'ew'
        if any(kw in n for kw in ['target', 'strike']):
            return 'target'
        return 'unknown'

    def _calculate_hyper_metrics(self) -> Dict[str, float]:
        metrics = {}
        total_possible = self._calculate_possible_cross_edges()
        metrics['cross_layer_density'] = (
            len(self.cross_layer_edges) / total_possible if total_possible > 0 else 0
        )
        metrics['layer_coupling_strength'] = self._calculate_coupling_strength()
        metrics['cross_layer_connectivity'] = self._calculate_cross_layer_connectivity()
        return metrics

    def _calculate_possible_cross_edges(self) -> int:
        total = 0
        layer_names = list(self.layers.keys())
        for i in range(len(layer_names)):
            for j in range(len(layer_names)):
                if i != j:
                    total += (len(self.layers[layer_names[i]].nodes()) *
                              len(self.layers[layer_names[j]].nodes()))
        return total

    def _calculate_coupling_strength(self) -> float:
        if not self.cross_layer_edges:
            return 0.0
        return sum(e['weight'] for e in self.cross_layer_edges) / len(self.cross_layer_edges)

    def _calculate_cross_layer_connectivity(self) -> float:
        cross_nodes = set()
        for edge in self.cross_layer_edges:
            cross_nodes.add((edge['source_node'], edge['source_layer']))
            cross_nodes.add((edge['target_node'], edge['target_layer']))
        total = sum(len(l.nodes()) for l in self.layers.values())
        return len(cross_nodes) / total if total > 0 else 0
