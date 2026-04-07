# detect_encoding.py
import chardet


def detect_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result


# 检测编码
file_path = '../data/raw/112.csv'
encoding_info = detect_file_encoding(file_path)
print(f"文件编码检测结果: {encoding_info}")

# 尝试用检测到的编码读取
try:
    encoding = encoding_info['encoding']
    confidence = encoding_info['confidence']
    print(f"建议编码: {encoding} (置信度: {confidence:.2%})")

    # 测试读取
    import pandas as pd

    df = pd.read_csv(file_path, encoding=encoding)
    print(f"✅ 使用 {encoding} 编码读取成功!")
    print(f"数据形状: {df.shape}")
    print("\n前3行数据:")
    print(df.head(3))

except Exception as e:
    print(f"❌ 使用 {encoding} 编码读取失败: {e}")