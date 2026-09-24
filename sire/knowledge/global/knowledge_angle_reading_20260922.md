---
id: K-angle-reading-liubobo-20260922
title: liubobo-angle-hall RS485 0x43 角度读取完整实现
domain: EncoderPlotter
kind: implementation
status: active
date: 2026-09-22
tags: 角度读取,RS485,0x43,DPT,DPB,liubobo-angle-hall,独立脚本,硬件验证
confidence: 0.99
---

## 概述

完成 `liubobo-angle-hall.py` 独立脚本的角度读取功能优化和硬件验证。脚本现已支持 RS485 0x43 双角度命令，能直接读取 DPT/DPB 编码器的内外圈角度数据。

## 改动清单

### 1. 角度命令修正 (L66)
```python
# 之前：EncoderRS485CommandAngle = 0x33
# 之后：EncoderRS485CommandAngle = 0x43
```
- **原因**：0x43 是 DPT/DPB 标准双角度命令
- **帧格式**：内圈(3B) + 外圈(3B) + 状态(1B) + CRC(1B) = 8 字节小端

### 2. 启动诊断增强 (L553-559)
```python
def startAngleContinuous(self, timeoutByteNum=8):  # 从 5 改为 8
    cfg = self._angleConfig(timeoutByteNum)
    print(f"[角度] 配置：接口={cfg.interface}, 波特率={cfg.baudRate}, 超时字节数={timeoutByteNum}")
    config_result, readout_result, status_result = self.startMultiInterfaceContinuous([cfg])
    print(f"[角度] 启动返回: config={config_result is not None}, readout={readout_result is not None}, status={status_result is not None}")
```
- 增加配置参数打印
- 启动返回值检查（三个返回值都应非空）
- 异常警告（任一返回值为空时打印）

### 3. 解析诊断增强 (L940-943)
```python
if mode == "angle":
    records, rejected = resolveAngleFrames(response)
    print(f"[角度] 解析: 有效={len(records)}, 空={rejected['empty']}, 错误={rejected['error']}, 长度异常={rejected['length']}, CRC={rejected['crc']}")
    print(f"[角度] 样本帧: {rejected['samples']}")
    if not records and any(rejected[key] for key in ("empty", "error", "length", "crc")):
        print(f"⚠️ [角度] 全部帧丢弃，帧长分布: {rejected['length_histogram']}")
```
- 打印解析统计（有效、空、错误、长度异常、CRC 各类数）
- 样本帧显示（调试帧格式差异）
- 帧长分布直方图（诊断异常帧）

## 硬件验证结果

**测试环境**：
- 设备：DPT 双圈编码器
- 读取器：Analyzer (serial=20260806083629, port=COM36)
- 系统：Windows 11, Python 3.12

**采集统计**：
| 指标 | 数值 |
|------|------|
| 采集行数 | 9034 条 |
| 内圈角度平均 | 17.440572° |
| 内圈波动范围 | ±0.000107° |
| 外圈角度平均 | 227.675376° |
| 外圈波动范围 | ±0.000021° |
| 数据稳定性 | ⭐⭐⭐⭐⭐ |

**输出格式**（TSV 表）：
```
index  inner_raw  outer_raw  inner_degree  outer_degree  inner_multi  status
1      812792     10610442   17.440624     227.675385    <空>         None
2      812792     10610442   17.440624     227.675385    <空>         None
...
```

## 使用流程

```bash
python liubobo-angle-hall.py
# 交互菜单出现，输入以下命令：

e                    # 进入再标定模式（需 ~1.5 秒）
start angle 2000     # 开始读取角度，采集频率 2000Hz
stop                 # 停止读取
q                    # 退出脚本
```

输出文件：`angle_YYYYMMDD_HHMMSS.txt` （脚本所在目录）

## 技术规格

| 项 | 规格 |
|----|------|
| **通讯接口** | RS485 双线 |
| **命令码** | 0x43（标准双角度） |
| **波特率** | 再标定态 4MHz / APP 态 2.5MHz |
| **帧周期** | 由采集频率决定（默认 6000Hz） |
| **角度精度** | 24 bit 小端 → 分辨率 360°/2^24 ≈ 0.0000214°/LSB |
| **数据格式** | 内圈(3B) + 外圈(3B) + 状态(1B) + CRC(1B) |
| **CRC 校验** | CRC8，校验值为 0 时通过 |

## 脚本独立性

- ✓ 无仓库依赖（不 import 本仓库任何模块）
- ✓ 仅依赖 pyserial 第三方库
- ✓ 可脱离项目环境单独运行
- ✓ 适合在测试环境/产线直连编码器

## 已验证的编码器型号

- ✓ DPT（双圈）— 验证通过
- ⚠ MPT（单圈）— 理论支持（回退 2.5MHz）
- ⚠ DPB（双圈）— 理论支持

---

**关键要点**：脚本现已可直接用于硬件角度读取，无需额外配置。从交互菜单启动 → 自动采集 → 导出 TSV 完整链路已验证。
