import numpy as np
from typing import Tuple, Dict, Text, List, Callable
import math
from .dimpc_utilts import MapInfo


veh_constrain = True


def solve_quadratic_equation(a, b, c):
    discriminant = b**2 - 4*a*c

    if discriminant > 0:
        # 两个实根
        x1 = (-b + math.sqrt(discriminant)) / (2*a)
        x2 = (-b - math.sqrt(discriminant)) / (2*a)
        assert x1 * x2 < 0
        return x1 if x1 >0 else x2
    elif discriminant == 0:
        # 一个实根
        x = -b / (2*a)
        return x
    else:
        # 无实根
        return "无实根"


class VData:
    def __init__(self,
                 vid: int = 0,
                 tx0: Tuple[int, np.ndarray] = (0, np.array([0, 0, 0])),
                 tdvp: Tuple[int, float, bool] = (0, 0, False),
                 tdvq: Tuple[int, float, bool] = (0, 0, False),
                 tdf: Tuple[int, Tuple[float, float]] = (0, (0, 0)),
                 otivp: Tuple[int, int, bool] = (0, 0, False),
                 otivq: Tuple[int, int, bool] = (0, 0, False),
                 T: int = 0,
                 safe_dist: float = 0.0,
                 d_i: int = 0,
                 veh_num: int = 0,
                 rho: float = 0,
                 sigma: float = 0,
                 road: Text = '',
                 last: bool = None,
                 neighbors: List[int] = None
                 ):
        self.vid: int = vid
        self.tx0: Tuple[int, np.ndarray] = tx0
        self.tdvp: Tuple[int, float, bool] = tdvp
        self.tdvq: Tuple[int, float, bool] = tdvq
        self.tdf: Tuple[int, Tuple[float, float]] = tdf
        self.otivp: Tuple[int, int, bool] = otivp
        self.otivq: Tuple[int, int, bool] = otivq
        self.T: int = T
        self.safe_dist: float = safe_dist
        self.d_i: int = d_i
        self.veh_num: int = veh_num
        self.rho: float = rho
        self.sigma: float = sigma
        self.road: Text = road
        self.last: bool = last
        self.neighbors: List[int] = neighbors

    def check(self):
        assert self.last is not None
        assert self.road != ''
        assert self.tx0[0] == 0
        assert self.d_i + 1 == self.veh_num
        assert self.T == self.tdf[0]


class TrajDataGenerator:

    def __init__(
        self,
        L1: float,
        L2: float,
        L3: float,
        dp: float,
        dq: float,
        veh_num: int,
        init_length: float,
        init_velocity: float,
        init_range: Tuple[float, float],
        init_velocity_range: Tuple[float, float],
        safe_dist: float = 10.0,
        rho: float = 1.0,
        sigma: float = 1.0,
        over_length: float = None,
        over_velocity: float = None
    ):
        self.L1: float = L1
        self.L2: float = L2
        self.L3: float = L3
        self.dp: float = dp
        self.dq: float = dq
        self.veh_num: int = veh_num
        self.init_length: float = init_length
        self.init_velocity: float = init_velocity
        self.init_range: Tuple[float, float] = init_range
        self.init_velocity_range: Tuple[float, float] = init_velocity_range
        self.safe_dist: float = safe_dist
        self.rho: float = rho
        self.sigma: float = sigma
        assert self.veh_num <= 2 * int(self.L1 / self.init_length)
        assert self.L1 < self.dp < self.L2 + self.L1
        assert self.dq == self.L1 + self.L2
        if over_length is None:
            self.over_length = self.init_length / np.sqrt(2)
        else:
            self.over_length = over_length
        if over_velocity is None:
            self.over_velocity = np.sqrt(2) * self.init_velocity
        else:
            self.over_velocity = over_velocity

    def gen_init_state(self) -> Tuple[Dict, Tuple]:
        assert self.veh_num <= 2 * int(self.L1 / self.init_length)
        max_veh = 2 * int(self.L1 / self.init_length)
        max_veh_one_one_road = int(self.L1 / self.init_length)
        all_points = {
            i: (
                'main' if i < max_veh_one_one_road else 'merge',
                0.5 * self.init_length +
                (i % max_veh_one_one_road) * self.init_length +
                np.random.uniform(self.init_range[0], self.init_range[1]),
                self.init_velocity + np.random.uniform(self.init_velocity_range[0], self.init_velocity_range[1])
            )
            for i in range(max_veh)
        }
        select_points = {
            v_id: all_points[i] for v_id, i in enumerate(np.random.choice([_ for _ in range(max_veh)], size=self.veh_num, replace=False))
        }
        order = tuple(sorted(select_points, key=lambda vid: select_points[vid][1], reverse=True))
        select_points_new = {idx: select_points[v_id] for idx, v_id in enumerate(order)}
        return select_points_new, tuple(reversed(select_points_new.keys()))

    def generate_all_vdata(self) -> Tuple[int, Dict[int, VData]]:
        init_states, order = self.gen_init_state()
        all_VDATA: Dict[int, VData] = {v_id: VData(
            vid=v_id,
            safe_dist=self.safe_dist,
            d_i=self.veh_num-1,
            veh_num=self.veh_num,
            rho=self.rho,
            sigma=self.sigma,
            last=True if v_id == order[0] else False
        ) for v_id in order}

        all_data_dict = {v_id: dict(
            road=init_states[v_id][0],
            init_pos=init_states[v_id][1],
            init_velocity=init_states[v_id][2],
            neighbors=[]
        ) for v_id in order}

        over_pos = [self.L1+self.L2+i*self.over_length for i in range(self.veh_num)]
        for v_id, pos in zip(order, over_pos):
            all_data_dict[v_id]['final_pos'] = pos

        # tf
        for v_id in order:
            all_data_dict[v_id]['tf'] = 2 * (all_data_dict[v_id]['final_pos'] - all_data_dict[v_id]['init_pos']) \
                                        / (all_data_dict[v_id]['init_velocity'] + self.over_velocity)
        # tf and tm
        tf = np.mean([data['tf'] for data in all_data_dict.values()])
        T = int(tf / 0.1)
        for i, v_id in enumerate(order):
            all_data_dict[v_id]['tf'] = int(tf / 0.1)
            # TODO: tm?
            all_data_dict[v_id]['tm'] = int((tf - 0.6 - 0.7 * i) / 0.1)
            all_VDATA[v_id].road = all_data_dict[v_id]['road']
            all_VDATA[v_id].T = T
            all_VDATA[v_id].tdf = (
                all_data_dict[v_id]['tf'],
                (all_data_dict[v_id]['final_pos'], all_data_dict[v_id]['final_pos'] + self.over_length)
            )
            all_VDATA[v_id].tx0 = \
                (0, np.array([all_data_dict[v_id]['init_pos'], all_data_dict[v_id]['init_velocity'], 0.0]))

        # before tm
        order_of_main = [v_id for v_id in order if all_data_dict[v_id]['road'] == 'main']
        for i, v_id in enumerate(order_of_main):
            if v_id != order_of_main[-1]:
                all_data_dict[v_id]['leader_before'] = order_of_main[i+1]
                all_data_dict[v_id]['neighbors'].append(order_of_main[i+1])
            if v_id != order_of_main[0]:
                all_data_dict[v_id]['is_leader_before'] = (all_data_dict[order_of_main[i-1]]['tm'], order_of_main[i-1])
                all_data_dict[v_id]['neighbors'].append(order_of_main[i-1])
        order_of_merge = [v_id for v_id in order if all_data_dict[v_id]['road'] == 'merge']
        for i, v_id in enumerate(order_of_merge):
            if v_id != order_of_merge[-1]:
                all_data_dict[v_id]['leader_before'] = order_of_merge[i+1]
                all_data_dict[v_id]['neighbors'].append(order_of_merge[i+1])
            if v_id != order_of_merge[0]:
                all_data_dict[v_id]['is_leader_before'] = (all_data_dict[order_of_merge[i-1]]['tm'], order_of_merge[i-1])
                all_data_dict[v_id]['neighbors'].append(order_of_merge[i-1])
        # after tm
        for i, v_id in enumerate(order):
            if v_id != order[-1]:
                all_data_dict[v_id]['leader_after'] = order[i+1]
                all_data_dict[v_id]['neighbors'].append(order[i+1])
            if v_id != order[0]:
                all_data_dict[v_id]['is_leader_after'] = (all_data_dict[order[i-1]]['tm'], order[i-1])
                all_data_dict[v_id]['neighbors'].append(order[i-1])

        for v_id in all_VDATA:
            all_VDATA[v_id].tdvp = (all_data_dict[v_id]['tm'], self.dp, True if 'leader_before' in all_data_dict[v_id] else False)
            all_VDATA[v_id].tdvq = (all_data_dict[v_id]['tm'], self.dq, True if 'leader_after' in all_data_dict[v_id] else False)
            all_VDATA[v_id].otivp = (all_data_dict[v_id]['is_leader_before'][0], all_data_dict[v_id]['is_leader_before'][1], True) \
                if 'is_leader_before' in all_data_dict[v_id] else (0, 0, False)
            all_VDATA[v_id].otivq = (all_data_dict[v_id]['is_leader_after'][0], all_data_dict[v_id]['is_leader_after'][1], True) \
                if 'is_leader_after' in all_data_dict[v_id] else (0, 0, False)
            all_VDATA[v_id].neighbors = all_data_dict[v_id]['neighbors']

        for v_id, vdata in all_VDATA.items():
            vdata.check()

        return T, all_VDATA


def gen_xs_ys(P_x: float, Q_x: float, _alpha: float, _L: float, _W: float) -> Tuple[Callable, Callable]:
    cos_alpha = np.cos(_alpha)
    sin_alpha = np.sin(_alpha)
    tan_alpha = np.tan(_alpha)
    tan_beta = _W / (Q_x - P_x)

    def _Xs(s: float) -> float:
        return s
        # if s <= P_x-_L/cos_alpha:
        #     return s + _L*(1/cos_alpha - 1)
        # elif P_x-_L/cos_alpha < s <= P_x:
        #     return P_x - _L + (s - P_x + _L / cos_alpha) * cos_alpha
        # else:
        #     return s

    def _Ys(s: float) -> float:
        if s <= P_x-_L:
            return -_W - _L * tan_alpha
        elif P_x-_L < s <= P_x:
            return s * tan_alpha + (-P_x * tan_alpha - _W)
        elif P_x < s <= Q_x:
            return -_W*(s-Q_x) / (P_x-Q_x)
        else:
            return 0

    return _Xs, _Ys


def gen_ramp_mapinfo(_Px: float, _Qx: float, _alpha: float, _L: float, _W: float) -> MapInfo:
    tan_alpha = np.tan(_alpha)
    over_length = 200
    _solid = list()
    _solid.append(dict(x=(0, _Qx+over_length), y=(0.5*_W, 0.5*_W)))
    _solid.append(dict(x=(0, _Px), y=(-0.5*_W, -0.5*_W)))
    _solid.append(dict(x=(_Qx, _Qx+over_length), y=(-0.5*_W, -0.5*_W)))
    _solid.append(dict(x=(0, _Px-_L), y=(-_L*tan_alpha-0.5*_W, -_L*tan_alpha-0.5*_W)))
    _solid.append(dict(x=(0, _Px-_L), y=(-_L*tan_alpha-1.5*_W, -_L*tan_alpha-1.5*_W)))
    _solid.append(dict(x=(_Px-_L, _Px), y=(-_L*tan_alpha-1.5*_W, -1.5*_W)))
    _solid.append(dict(x=(_Px-_L, _Px), y=(-_L*tan_alpha-0.5*_W, -0.5*_W)))
    _solid.append(dict(x=(_Px, _Qx), y=(-1.5*_W, -1.5*_W)))
    _solid.append(dict(x=(_Qx, _Qx), y=(-1.5*_W, -0.5*_W)))
    _dash = list()
    _dash.append(dict(x=(0, _Qx+over_length), y=(0, 0)))
    _dash.append(dict(x=(0, _Px-_L), y=(-_W-_L*tan_alpha, -_W-_L*tan_alpha)))
    _dash.append(dict(x=(_Px-_L, _Px), y=(-_W-_L*tan_alpha, -_W)))
    _dash.append(dict(x=(_Px, _Qx), y=(-_W, -0)))
    _dash.append(dict(x=(_Qx, _Qx+over_length), y=(-0, -0)))
    return MapInfo(_solid, _dashed=_dash)


# o = TrajDataGenerator(100, 50, 150, 110, 150, 9, 20, 15, (-2, 2), (-1, 1))
# all_vdata = o.generate_all_vdata()

if __name__ == "__main__":
    import matplotlib.pyplot as plt

    xs, ys = gen_xs_ys(110, 150, np.deg2rad(10), 10, 4.0)
    s = np.arange(0, 200)
    x = np.array(
        [xs(_) for _ in s]
    )
    y = np.array(
        [ys(_) for _ in s]
    )
    fig, ax = plt.subplots()
    ax.set_xlim(0, 210)
    # ax.set_ylim(-20, 15)
    ax.set_aspect('equal')
    plt.scatter(x, y)
    plt.show()
