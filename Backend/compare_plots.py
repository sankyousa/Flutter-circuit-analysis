
# compare_plots.py (V4 - 修正了相位解卷绕的计算bug)

import numpy as np
import matplotlib.pyplot as plt
from control import TransferFunction
import re

def load_ltspice_data(filepath):
    """
    一个强大的自定义函数，用于解析LTspice导出的 "freq (mag,phase)" 格式的数据。
    """
    freqs, mags, phases = [], [], []
    with open(filepath, 'r', encoding='latin1') as f:
        next(f)
        for line in f:
            try:
                parts = line.strip().split('\t')
                if len(parts) != 2:
                    continue
                freq_str, complex_str = parts
                numbers = re.findall(r"[-+]?\d*\.\d+e*[-+]?\d*", complex_str)
                if len(numbers) == 2:
                    freqs.append(float(freq_str))
                    mags.append(float(numbers[0]))
                    phases.append(float(numbers[1]))
            except (ValueError, IndexError) as e:
                print(f"警告：跳过无法解析的行: '{line.strip()}'，错误: {e}")
                continue
    return np.array(freqs), np.array(mags), np.unwrap(np.array(phases), period=360)


def get_bode_data(system, omega_range):
    """一个辅助函数，用于从control库计算波特图的数值数据"""
    mag, phase_rad, omega = system.frequency_response(omega_range)
    mag_db = 20 * np.log10(mag)
    
    # <<< MODIFIED >>>: 修正了相位处理的顺序
    # 应该先对弧度制的相位进行解卷绕，然后再转换为角度制
    phase_unwrapped_rad = np.unwrap(phase_rad)
    phase_deg = np.rad2deg(phase_unwrapped_rad)
    # <<< MODIFICATION END >>>
    
    freq_hz = omega / (2 * np.pi)
    return freq_hz, mag_db, phase_deg

# --- 第1部分: 定义您App的传递函数 ---
#
# 在这里粘贴您从App后端终端复制的系数
# 这是一个示例，请用您的实际数据替换
num_coeffs = [11.0, 12.0, 24.0, 3.0, 1.0]
den_coeffs = [11.0, 35.0, 50.0, 54.0, 9.0, 2.0]


# --- 第2部分: 加载从LTspice导出的数据 ---
#
try:
    freq_ltspice_hz, mag_ltspice_db, phase_ltspice_deg = load_ltspice_data('ltspice_data.txt')
    ltspice_data_loaded = True
except Exception as e:
    print(f"读取LTspice数据失败，请检查文件路径: {e}")
    ltspice_data_loaded = False


# --- 第3部分: 在同一张图上绘制两个数据集 ---
#
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
fig.suptitle('Bode Plot Comparison: My App vs. LTspice', fontsize=16)

# 绘制您App的曲线
if num_coeffs and den_coeffs:
    sys_app = TransferFunction(num_coeffs, den_coeffs)
    freq_range_hz = np.logspace(-6, 3, 1000)
    omega_range = freq_range_hz * 2 * np.pi

    app_freq, app_mag, app_phase = get_bode_data(sys_app, omega_range)
    ax1.semilogx(app_freq, app_mag, label='My App', color='dodgerblue', linewidth=2)
    ax2.semilogx(app_freq, app_phase, label='My App', color='dodgerblue', linewidth=2)


# 绘制LTspice的曲线
if ltspice_data_loaded:
    ax1.semilogx(freq_ltspice_hz, mag_ltspice_db, label='LTspice',
                 color='orangered', linestyle='--', linewidth=2)
    ax2.semilogx(freq_ltspice_hz, phase_ltspice_deg, label='LTspice',
                 color='orangered', linestyle='--', linewidth=2)

# 设置图形格式
ax1.set_ylabel('Magnitude (dB)')
ax1.grid(True, which='both', linestyle=':')
ax1.legend()

ax2.set_xlabel('Frequency (Hz)')
ax2.set_ylabel('Phase (deg)')
ax2.grid(True, which='both', linestyle=':')
ax2.legend()

plt.savefig('comparison_bode_plot.png', dpi=300)
print("对比图 'comparison_bode_plot.png' 已成功保存。")

plt.show()