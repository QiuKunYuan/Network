# src/data_processor.py
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
import os
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False


class AFSIMDataProcessor:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df = self._load_data_with_encoding()
        self.platforms = {}
        self._preprocess_data()

    def _detect_encoding(self) -> str:
        """自动检测文件编码（优先 gb18030，再用 chardet 兜底）"""
        # 先用原始字节快速判断是否为 GB 系编码
        try:
            with open(self.file_path, 'rb') as f:
                raw_data = f.read(10000)
            # 尝试 gb18030 解码前几百字节，成功则直接返回
            raw_data[:500].decode('gb18030')
            print("快速检测：文件编码为 gb18030")
            return 'gb18030'
        except (UnicodeDecodeError, Exception):
            pass

        if HAS_CHARDET:
            try:
                with open(self.file_path, 'rb') as f:
                    raw_data = f.read(10000)
                result = chardet.detect(raw_data)
                encoding = result['encoding']
                confidence = result['confidence']
                print(f"chardet 检测到文件编码: {encoding} (置信度: {confidence:.2%})")
                return encoding if encoding else 'utf-8'
            except Exception as e:
                print(f"编码检测失败: {e}, 使用默认编码 utf-8")
        return 'utf-8'

    def _load_data_with_encoding(self) -> pd.DataFrame:
        """使用自动检测的编码加载数据"""
        # gb18030 是 gbk/gb2312 的超集，优先放在最前面
        encodings_to_try = ['gb18030', 'utf-8', 'gbk', 'gb2312', 'latin1', 'iso-8859-1', 'cp1252']

        detected_encoding = self._detect_encoding()
        # 将检测到的编码插到最前面（去重）
        if detected_encoding and detected_encoding not in encodings_to_try:
            encodings_to_try.insert(0, detected_encoding)
        elif detected_encoding and encodings_to_try[0] != detected_encoding:
            encodings_to_try.remove(detected_encoding)
            encodings_to_try.insert(0, detected_encoding)

        for encoding in encodings_to_try:
            try:
                print(f"尝试使用 {encoding} 编码读取文件...")
                df = pd.read_csv(self.file_path, encoding=encoding, low_memory=False)
                print(f"✅ 使用 {encoding} 编码读取成功!")
                # 规范化列名：去除首尾空格
                df.columns = [c.strip() for c in df.columns]
                print(f"列名列表: {list(df.columns)}")
                return df
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"❌ {encoding} 编码其他错误: {e}")
                continue

        try:
            print("尝试使用错误处理方式读取...")
            df = pd.read_csv(self.file_path, encoding='utf-8', errors='replace', low_memory=False)
            df.columns = [c.strip() for c in df.columns]
            print("✅ 使用错误处理方式读取成功")
            return df
        except Exception as e:
            raise Exception(f"所有编码方式都失败: {e}")

    def _preprocess_data(self):
        """数据预处理"""
        print(f"数据加载成功: {len(self.df)} 行, {len(self.df.columns)} 列")

        # 将时间列转换为数值型（AFSIM 时间列为秒数，可能读入为 object）
        time_col = self.df.columns[0]  # 第一列为时间列
        if self.df[time_col].dtype == object:
            self.df[time_col] = pd.to_numeric(self.df[time_col], errors='coerce')
            print(f"时间列 '{time_col}' 已转换为数值型，NaN 行数: {self.df[time_col].isna().sum()}")
        print(f"时间范围: {self.df[time_col].min()} ~ {self.df[time_col].max()} 秒")

    def extract_communication_links(self) -> List[Tuple[str, str, float]]:
        """提取通信链路"""
        print("提取通信链路...")
        links = []

        # 方法1: 从MsgPartStatus中提取通信关系
        comm_data = self.df[
            (self.df['type（信息类型）'] == 'MsgPartStatus') &
            (self.df['component'] == 'comm')
            ]

        # 找到活跃的通信组件
        active_comms = comm_data[comm_data['8'] == 'TRUE']

        for platform in active_comms['platform（所有者或源平台）'].unique():
            if pd.notna(platform):
                # 根据平台类型推断通信关系
                if 'radar' in platform.lower():
                    links.append((platform, 'command_center', 0.8))
                elif 'sam' in platform.lower():
                    links.append((platform, 'command_center', 0.9))
                elif 'command' in platform.lower() or 'cmdr' in platform.lower():
                    # 指挥节点之间的通信
                    links.append((platform, 'radar_network', 1.0))

        # 方法2: 从平台层级推断通信
        hierarchy = self.extract_platform_hierarchy()
        for subordinate, commander in hierarchy.items():
            if pd.notna(subordinate) and pd.notna(commander):
                links.append((subordinate, commander, 0.7))

        print(f"提取到 {len(links)} 个通信链路")
        return links

    def extract_sensor_detections(self) -> List[Tuple[str, str, float]]:
        """提取传感器探测关系"""
        print("提取传感器探测关系...")
        detections = []

        # 从MsgSensorDetectionChange中提取
        sensor_data = self.df[self.df['type（信息类型）'] == 'MsgSensorDetectionChange']

        for _, row in sensor_data.iterrows():
            sensor = row['platform（所有者或源平台）']
            target = row['interactor']
            if pd.notna(sensor) and pd.notna(target) and row.get('8') == 'TRUE':
                detections.append((sensor, target, 1.0))

        # 从传感器组件状态推断
        sensor_parts = self.df[
            (self.df['type（信息类型）'] == 'MsgPartStatus') &
            (self.df['component'].isin(['sensor', 'ew_radar', 'acq_radar', 'esm']))
            ]

        active_sensors = sensor_parts[sensor_parts['8'] == 'TRUE']
        for platform in active_sensors['platform（所有者或源平台）'].unique():
            if pd.notna(platform):
                # 雷达探测空中目标
                if 'radar' in platform.lower():
                    detections.append((platform, 'air_targets', 0.6))
                # ESM探测辐射源
                elif 'esm' in platform.lower() or 'soj' in platform.lower():
                    detections.append((platform, 'emitter_sources', 0.5))

        print(f"提取到 {len(detections)} 个传感器探测")
        return detections

    def extract_platform_hierarchy(self) -> Dict[str, str]:
        """提取平台层级关系"""
        print("提取平台层级关系...")
        hierarchy = {}

        platform_info = self.df[self.df['type（信息类型）'] == 'MsgPlatformInfo']

        for _, row in platform_info.iterrows():
            platform_id = row['platform（所有者或源平台）']
            component = row.get('component', '')

            if pd.notna(component) and 'default:' in str(component):
                owner = str(component).split('default:')[-1].strip()
                if pd.notna(platform_id) and pd.notna(owner) and platform_id != owner:
                    hierarchy[platform_id] = owner

        print(f"提取到 {len(hierarchy)} 个层级关系")
        if hierarchy:
            print("示例关系:")
            for platform, owner in list(hierarchy.items())[:3]:
                print(f"  {platform} -> {owner}")

        return hierarchy

    def get_all_platforms(self) -> List[str]:
        """获取所有平台ID"""
        platforms = self.df['platform（所有者或源平台）'].dropna().unique()
        platform_list = [p for p in platforms if p and p != '']
        print(f"发现 {len(platform_list)} 个唯一平台")
        return platform_list

    def get_data_info(self):
        """获取数据基本信息"""
        info = {
            'total_rows': len(self.df),
            'total_columns': len(self.df.columns),
            'column_names': list(self.df.columns),
            'message_types': self.df[
                'type（信息类型）'].value_counts().to_dict() if 'type（信息类型）' in self.df.columns else {},
            'platforms_count': self.df[
                'platform（所有者或源平台）'].nunique() if 'platform（所有者或源平台）' in self.df.columns else 0
        }
        return info

    def analyze_message_types(self):
        """分析信息类型分布"""
        if 'type（信息类型）' in self.df.columns:
            msg_counts = self.df['type（信息类型）'].value_counts()
            print("\n信息类型分布:")
            for msg_type, count in msg_counts.items():
                print(f"  {msg_type}: {count} 行")
            return msg_counts
        return {}

    def get_time_windows(self, window_size: float = 100.0, step: float = 50.0):
        """
        将全量数据按照时间窗口切分
        :param window_size: 每个时间窗口的长度（秒）
        :param step: 窗口滑动的步长（秒）
        """
        # AFSIM CSV 通常第一列是时间戳，或者你可以指定时间列名
        time_col = self.df.columns[0]
        max_time = self.df[time_col].max()

        windows = []
        import numpy as np
        for start in np.arange(0, max_time, step):
            end = start + window_size
            subset = self.df[(self.df[time_col] >= start) & (self.df[time_col] < end)].copy()
            if not subset.empty:
                windows.append((start, end, subset))
        print(f"共生成 {len(windows)} 个时间窗口快照")
        return windows

    # 构造动态图部分
    def extract_interactions(self, keyword1='soj', keyword2='ew_radar', output_path='interactions.csv'):
        """
        筛选两个实体关键字之间有交互的数据并保存
        """
        # 确保列名存在（防止列名不一致）
        platform_col = 'platform（所有者或源平台）'
        interactor_col = 'interactor'

        if platform_col not in self.df.columns or interactor_col not in self.df.columns:
            print(f"错误：数据中未找到必要的列 {platform_col} 或 {interactor_col}")
            return None

        # 构建筛选掩码
        mask = (
                (self.df[platform_col].str.contains(keyword1, case=False, na=False) &
                 self.df[interactor_col].str.contains(keyword2, case=False, na=False)) |
                (self.df[platform_col].str.contains(keyword2, case=False, na=False) &
                 self.df[interactor_col].str.contains(keyword1, case=False, na=False))
        )

        result_df = self.df[mask]
        print(f"从 {len(self.df)} 条数据中筛选出 {len(result_df)} 条交互记录")

        if output_path:
            result_df.to_csv(output_path, index=False)
            print(f"结果已保存至: {output_path}")

        return result_df

