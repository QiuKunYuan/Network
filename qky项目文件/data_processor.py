# src/data_processor.py
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
import os

try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False


# ── 列名映射表：支持中文全角括号列名和纯英文列名两种格式 ──────────────
_COL_ALIASES = {
    'time':      ['time（时间）', 'time', 'Time', 'timestamp'],
    'type':      ['type（信息类型）', 'type', 'Type', 'msg_type'],
    'platform':  ['platform（所有者或源平台）', 'platform', 'Platform', 'owner'],
    'interactor':['interactor', 'Interactor', 'target'],
    'component': ['component', 'Component'],
    'track_id':  ['track id', 'track_id', 'TrackId'],
    'col8':      ['8'],   # 状态列（TRUE/FALSE）
}


def _find_col(df: pd.DataFrame, key: str) -> Optional[str]:
    """在 DataFrame 中查找列名，支持别名映射，找不到返回 None"""
    for alias in _COL_ALIASES.get(key, [key]):
        if alias in df.columns:
            return alias
    return None


class AFSIMDataProcessor:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df = self._load_data_with_encoding()
        self.platforms = {}
        # 列名快捷访问（避免每次都查找）
        self._col = {k: _find_col(self.df, k) for k in _COL_ALIASES}
        self._preprocess_data()

    # ─────────────────────────────────────────────
    # 数据加载
    # ─────────────────────────────────────────────

    def _detect_encoding(self) -> str:
        """自动检测文件编码（优先 gb18030，再用 chardet 兜底）"""
        try:
            with open(self.file_path, 'rb') as f:
                raw_data = f.read(10000)
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
        encodings_to_try = ['gb18030', 'utf-8', 'gbk', 'gb2312', 'latin1', 'iso-8859-1', 'cp1252']

        detected_encoding = self._detect_encoding()
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
                df.columns = [c.strip() for c in df.columns]
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

        # 时间列数值化
        time_col = self._col.get('time') or self.df.columns[0]
        if self.df[time_col].dtype == object:
            self.df[time_col] = pd.to_numeric(self.df[time_col], errors='coerce')
            nan_count = self.df[time_col].isna().sum()
            if nan_count > 0:
                print(f"时间列 '{time_col}' 转换后 NaN 行数: {nan_count}，已丢弃")
                self.df = self.df.dropna(subset=[time_col])
        print(f"时间范围: {self.df[time_col].min():.1f} ~ {self.df[time_col].max():.1f} 秒")

        # 打印消息类型分布（帮助调试）
        type_col = self._col.get('type')
        if type_col:
            msg_types = self.df[type_col].value_counts()
            print(f"消息类型分布（前10）:")
            for t, c in msg_types.head(10).items():
                print(f"  {t}: {c}")

    # ─────────────────────────────────────────────
    # 数据提取（健壮版）
    # ─────────────────────────────────────────────

    def _get_col(self, key: str) -> Optional[str]:
        """安全获取列名，找不到返回 None"""
        return self._col.get(key)

    def _filter_by_type(self, msg_type: str) -> pd.DataFrame:
        """按消息类型过滤，列名不存在时返回空 DataFrame"""
        col = self._get_col('type')
        if col is None:
            return pd.DataFrame()
        return self.df[self.df[col] == msg_type]

    def extract_platform_hierarchy(self) -> Dict[str, str]:
        """提取平台层级关系（从 MsgPlatformInfo 的 component 字段解析 default:xxx）"""
        print("提取平台层级关系...")
        hierarchy = {}

        platform_col = self._get_col('platform')
        component_col = self._get_col('component')
        if not platform_col or not component_col:
            print("  ⚠️ 缺少 platform 或 component 列，跳过层级提取")
            return hierarchy

        platform_info = self._filter_by_type('MsgPlatformInfo')
        for _, row in platform_info.iterrows():
            platform_id = row[platform_col]
            component = str(row.get(component_col, ''))
            if 'default:' in component:
                owner = component.split('default:')[-1].strip()
                if pd.notna(platform_id) and owner and platform_id != owner:
                    hierarchy[platform_id] = owner

        print(f"提取到 {len(hierarchy)} 个层级关系")
        if hierarchy:
            for p, o in list(hierarchy.items())[:3]:
                print(f"  {p} -> {o}")
        return hierarchy

    def extract_communication_links(self) -> List[Tuple[str, str, float]]:
        """提取通信链路"""
        print("提取通信链路...")
        links = []

        platform_col = self._get_col('platform')
        component_col = self._get_col('component')
        col8 = self._get_col('col8')

        if platform_col and component_col:
            type_col = self._get_col('type')
            comm_mask = (
                (self.df[type_col] == 'MsgPartStatus') &
                (self.df[component_col] == 'comm')
            ) if type_col else pd.Series(False, index=self.df.index)

            comm_data = self.df[comm_mask]
            if col8:
                active_comms = comm_data[comm_data[col8].astype(str).str.upper() == 'TRUE']
            else:
                active_comms = comm_data

            for platform in active_comms[platform_col].dropna().unique():
                p = str(platform).lower()
                if 'radar' in p:
                    links.append((platform, 'command_center', 0.8))
                elif 'sam' in p:
                    links.append((platform, 'command_center', 0.9))
                elif 'cmdr' in p or 'command' in p or 'iads' in p:
                    links.append((platform, 'radar_network', 1.0))

        # 从层级关系补充通信链路
        hierarchy = self.extract_platform_hierarchy()
        for subordinate, commander in hierarchy.items():
            links.append((subordinate, commander, 0.7))

        print(f"提取到 {len(links)} 个通信链路")
        return links

    def extract_sensor_detections(self) -> List[Tuple[str, str, float]]:
        """提取传感器探测关系"""
        print("提取传感器探测关系...")
        detections = []

        platform_col = self._get_col('platform')
        interactor_col = self._get_col('interactor')
        col8 = self._get_col('col8')

        if platform_col and interactor_col:
            sensor_data = self._filter_by_type('MsgSensorDetectionChange')
            for _, row in sensor_data.iterrows():
                sensor = row[platform_col]
                target = row[interactor_col]
                status = str(row.get(col8, '')).upper() if col8 else 'TRUE'
                if pd.notna(sensor) and pd.notna(target) and status == 'TRUE':
                    detections.append((str(sensor), str(target), 1.0))

        # 从活跃传感器组件补充
        component_col = self._get_col('component')
        type_col = self._get_col('type')
        if platform_col and component_col and type_col:
            sensor_parts = self.df[
                (self.df[type_col] == 'MsgPartStatus') &
                (self.df[component_col].isin(['sensor', 'ew_radar', 'acq_radar', 'esm', 'radar']))
            ]
            if col8:
                active = sensor_parts[sensor_parts[col8].astype(str).str.upper() == 'TRUE']
            else:
                active = sensor_parts

            for platform in active[platform_col].dropna().unique():
                p = str(platform).lower()
                if 'radar' in p:
                    detections.append((platform, 'air_targets', 0.6))
                elif 'esm' in p or 'soj' in p:
                    detections.append((platform, 'emitter_sources', 0.5))

        print(f"提取到 {len(detections)} 个传感器探测")
        return detections

    def extract_weapon_engagements(self) -> List[Tuple[str, str, float]]:
        """提取武器打击关系（MsgWeaponFired）"""
        print("提取武器打击关系...")
        engagements = []
        platform_col = self._get_col('platform')
        interactor_col = self._get_col('interactor')
        if not platform_col or not interactor_col:
            return engagements

        weapon_data = self._filter_by_type('MsgWeaponFired')
        for _, row in weapon_data.iterrows():
            launcher = row[platform_col]
            target = row[interactor_col]
            if pd.notna(launcher) and pd.notna(target):
                engagements.append((str(launcher), str(target), 1.0))

        print(f"提取到 {len(engagements)} 个武器打击关系")
        return engagements

    def extract_jamming_relations(self) -> List[Tuple[str, str, float]]:
        """提取电子战干扰关系（MsgJammingRequestInitiated）"""
        print("提取电子战干扰关系...")
        jammings = []
        platform_col = self._get_col('platform')
        interactor_col = self._get_col('interactor')
        if not platform_col or not interactor_col:
            return jammings

        jamming_data = self._filter_by_type('MsgJammingRequestInitiated')
        for _, row in jamming_data.iterrows():
            jammer = row[platform_col]
            target = row[interactor_col]
            if pd.notna(jammer) and pd.notna(target):
                jammings.append((str(jammer), str(target), 0.9))

        print(f"提取到 {len(jammings)} 个干扰关系")
        return jammings

    def get_all_platforms(self) -> List[str]:
        """获取所有平台ID"""
        platform_col = self._get_col('platform')
        if not platform_col:
            return []
        platforms = self.df[platform_col].dropna().unique()
        platform_list = [str(p) for p in platforms if p and str(p).strip()]
        print(f"发现 {len(platform_list)} 个唯一平台")
        return platform_list

    def get_data_info(self) -> Dict[str, Any]:
        """获取数据基本信息"""
        type_col = self._get_col('type')
        platform_col = self._get_col('platform')
        return {
            'total_rows': len(self.df),
            'total_columns': len(self.df.columns),
            'column_names': list(self.df.columns),
            'message_types': self.df[type_col].value_counts().to_dict() if type_col else {},
            'platforms_count': self.df[platform_col].nunique() if platform_col else 0,
        }

    def get_time_windows(self, window_size: float = 120.0, step: float = 60.0):
        """将全量数据按时间窗口切分"""
        time_col = self._get_col('time') or self.df.columns[0]
        max_time = self.df[time_col].max()
        min_time = self.df[time_col].min()

        windows = []
        for start in np.arange(min_time, max_time, step):
            end = start + window_size
            subset = self.df[(self.df[time_col] >= start) & (self.df[time_col] < end)].copy()
            if not subset.empty:
                windows.append((start, end, subset))

        print(f"共生成 {len(windows)} 个时间窗口快照（窗口={window_size}s，步长={step}s）")
        return windows

    def extract_interactions(self, keyword1='soj', keyword2='ew_radar', output_path='interactions.csv'):
        """筛选两个实体关键字之间有交互的数据并保存"""
        platform_col = self._get_col('platform')
        interactor_col = self._get_col('interactor')
        if not platform_col or not interactor_col:
            print(f"错误：数据中未找到必要的列")
            return None

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
