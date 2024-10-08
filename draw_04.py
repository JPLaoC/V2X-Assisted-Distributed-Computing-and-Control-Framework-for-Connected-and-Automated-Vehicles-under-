"""
平均计算时间、迭代次数
"""
import matplotlib.pyplot as plt
from utilits import *
import numpy as np
import matplotlib as mpl
from typing import Dict, Text, List


WHAT = '12'
LANG = 'EN'
plt.rcParams.update({'font.size': 10,
                     "text.usetex": True})
plt.rcParams['font.family'] = 'Times New Roman'


def extract_data(_all_info) -> Dict:
    _new_data = {v_id: dict() for v_id in _all_info.keys()}
    for v_id, _data in _all_info.items():
        _new_data[v_id]['run_time'] = np.sum(_data['run_time'], axis=1)
        _new_data[v_id]['iter_times'] = np.sum(_data['iter_times'], axis=1)

    _run_time_mat = np.vstack([
        _new_data[v_id]['run_time'] for v_id in _new_data.keys()
    ])
    _iter_times_mat = np.vstack([
        _new_data[v_id]['iter_times'] for v_id in _new_data.keys()
    ])
    return dict(run_time=_run_time_mat, iter_times=_iter_times_mat)


info_dict = {
    'proposed': PickleRead('output_dir/solve_info/osqp_solve_info_T'),
    'OSQP-CS': PickleRead('output_dir/solve_info/osqp_solve_info_cs_T'),
    'IPOPT': PickleRead('output_dir/solve_info/nlp_solve_info_T'),
    'LD-IPOPT': PickleRead('output_dir/solve_info/lnlp_solve_info_T'),
    'SQP': PickleRead('output_dir/solve_info/sqp_solve_info_T'),
}

# 定义数据
# algorithms = ['proposed', 'OSQP-CS']
# indicators = {'T cross': 'T', '1 round': '1', '2 round': '2', '3 round': '3'}
algorithms = ['Our', 'OSQP-CS', 'IPOPT', 'LD-IPOPT', 'SQP']
indicators = {'1 round': '4', '2 round': '8', '3 round': '12', 'T cross': 'T'}
indicators2CN = {'1 round': '十字-4车辆', '2 round': '十字-8车辆', '3 round': '十字-12车辆', 'T cross': 'T形-3车辆'}
all_data = np.zeros((len(algorithms), len(indicators)))
for ind_idx, ind_name in enumerate(indicators.keys()):
    info_dict = {
        'proposed': PickleRead('output_dir/solve_info/osqp_solve_info_{}'.format(indicators[ind_name])),
        'OSQP-CS': PickleRead('output_dir/solve_info/osqp_solve_info_cs_{}'.format(indicators[ind_name])),
        'IPOPT': PickleRead('output_dir/solve_info/nlp_solve_info_{}'.format(indicators[ind_name])),
        'LD-IPOPT': PickleRead('output_dir/solve_info/lnlp_solve_info_{}'.format(indicators[ind_name])),
        'SQP': PickleRead('output_dir/solve_info/sqp_solve_info_{}'.format(indicators[ind_name])),
    }
    if info_dict['SQP'] == None:
        info_dict['SQP'] = dict()
        for v_inx, v_data in info_dict['proposed'].items():
            info_dict['SQP'][v_inx] = {}
            for _str, _data in v_data.items():
                info_dict['SQP'][v_inx][_str] = np.zeros_like(_data)
        # info_dict['SQP']
    indicator_data = []
    for alg_name, alg_data in info_dict.items():
        mean_run_time = []
        for v_data in alg_data.values():
            mean_run_time.append(np.mean(v_data['run_time']))
        indicator_data.append(1000 * np.mean(mean_run_time))
    all_data[:, ind_idx] = np.array(indicator_data)

# 创建一个figure对象，设置画布大小
fig = plt.figure(figsize=(7, 2.5))

# 创建一个axes对象
ax = fig.add_subplot()

# 设置柱状图的宽度
width = 0.18

# 绘制柱状图
alg_names = [name for name in indicators.keys()]
# for i in range(len(indicators)):
#     ax.bar(np.arange(len(algorithms)) + i * width, all_data[:, i], width, label=alg_names[i])
for i in range(len(algorithms)):
    rects = ax.barh(np.arange(len(indicators)) + i * width, all_data[i, :], width, label=algorithms[i] if LANG == 'EN' else en_to_cn(algorithms[i]))
    if algorithms[i] == 'Our' or algorithms[i] == 'OSQP-CS':
        for ii, rect in enumerate(rects):
            if ii == 0 or 1:
                height = rect.get_width()
                ax.annotate('{:5.3f}'.format(height),
                            xy=(height, rect.get_y()),
                            xytext=(15, -2),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=8)  # 设置字体大小为10
                # ax.annotate('',
                #             xy=(rect.get_x() + rect.get_width() / 2, height),
                #             xytext=(rect.get_x() + rect.get_width() / 2, height + 0.5),
                #             arrowprops=dict(arrowstyle='->'))

# 设置x轴刻度和标签
ax.set_yticks(np.arange(len(indicators)) + width * 2)
ax.set_yticklabels([(indicators2CN[_] if LANG == 'CN' else indicators[_]) for _ in indicators])
ax.set_xlabel('控制时刻平均计算时间[$\mathrm{ms}$]' if LANG == 'CN' else 'average computational time[ms]')
plt.grid()
ax.legend()
plt.show()
# 添加图例


plt.savefig('output_dir/figs/average_run_time.svg')
# 显示图形


################################################
algorithms = ['proposed', 'OSQP-CS', 'IPOPT', 'LD-IPOPT', 'SQP']
indicators = {'1 round': '4', '2 round': '8', '3 round': '12', 'T cross': 'T'}
indicators2CN = {'1 round': '十字-4车辆', '2 round': '十字-8车辆', '3 round': '十字-12车辆', 'T cross': 'T形-3车辆'}
all_data = np.zeros((len(algorithms), len(indicators)))
for ind_idx, ind_name in enumerate(indicators.keys()):
    info_dict = {
        'proposed': PickleRead('output_dir/solve_info/osqp_solve_info_{}'.format(indicators[ind_name])),
        'OSQP-CS': PickleRead('output_dir/solve_info/osqp_solve_info_cs_{}'.format(indicators[ind_name])),
        'IPOPT': PickleRead('output_dir/solve_info/nlp_solve_info_{}'.format(indicators[ind_name])),
        'LD-IPOPT': PickleRead('output_dir/solve_info/lnlp_solve_info_{}'.format(indicators[ind_name])),
        'SQP': PickleRead('output_dir/solve_info/sqp_solve_info_{}'.format(indicators[ind_name])),
    }
    if info_dict['SQP'] == None:
        info_dict['SQP'] = dict()
        for v_inx, v_data in info_dict['proposed'].items():
            info_dict['SQP'][v_inx] = {}
            for _str, _data in v_data.items():
                info_dict['SQP'][v_inx][_str] = np.zeros_like(_data)
    indicator_data = []
    for alg_name, alg_data in info_dict.items():
        mean_run_time = []
        for v_data in alg_data.values():
            mean_run_time.append(np.sum(v_data['run_time']))
        indicator_data.append(np.sum(mean_run_time))
    all_data[:, ind_idx] = np.array(indicator_data)

# 创建一个figure对象，设置画布大小
fig = plt.figure(figsize=(7, 2.5))

# 创建一个axes对象
ax = fig.add_subplot()

# 设置柱状图的宽度
width = 0.18

# 绘制柱状图
alg_names = [name for name in indicators.keys()]
# for i in range(len(indicators)):
#     ax.bar(np.arange(len(algorithms)) + i * width, all_data[:, i], width, label=alg_names[i])
for i in range(len(algorithms)):
    # ax.bar(np.arange(len(indicators)) + i * width, all_data[i, :], width, label=algorithms[i])
    rects = ax.barh(np.arange(len(indicators)) + i * width, all_data[i, :], width, label=algorithms[i] if LANG == 'EN' else en_to_cn(algorithms[i]))
    if algorithms[i] == 'proposed' or algorithms[i] == 'OSQP-CS':
        for ii, rect in enumerate(rects):
            if ii == 0 or 1:
                height = rect.get_width()
                ax.annotate('{:5.3f}'.format(height),
                            xy=(height, rect.get_y()),
                            xytext=(15, -2),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=8)  # 设置字体大小为10

# 设置x轴刻度和标签
ax.set_yticks(np.arange(len(indicators)) + width * 2)
ax.set_yticklabels([indicators2CN[_] for _ in indicators])

# 设置标题和轴标签
# ax.set_title('Comparison of Algorithms')
# ax.set_xlabel('Algorithms')
ax.set_xlabel('总计算时间[$\mathrm{s}$]')

# 添加图例
ax.legend()
plt.grid()
plt.savefig('output_dir/figs/total_run_time.svg')
# 显示图形
plt.show()
