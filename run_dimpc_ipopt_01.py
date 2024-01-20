from dynamic_models import KinematicModel
from all_solvers import DistributedMPCIPOPT
from utilits import *
import numpy as np

mpc_config = DistributedMPCIPOPT.default_config
mpc_config['run_iter'] = 5
mpc_config['safe_factor'] = 3.5
mpc_config['safe_th'] = 1.8
mpc_config['pred_len'] = 30
mpc_config['other_veh_num'] = 3
mpc_config['comfort'] = 1.5
mpc_config['warm_start'] = False
mpc_config['Qu'] = 0.3 * np.diag([1.0, 0.5])

KinematicModel.initialize(KinematicModel.default_config)
DistributedMPCIPOPT.initialize(DistributedMPCIPOPT.default_config)


# load traj
# log_file = np.load("output_dir/traj_log/cross_double_3_round")

# trajs, step_num, traj_info, map_info = multi_cross(_points=8)
trajs, _, info_round, map_info = cross_traj_double_lane(
    _speed=5.5,
    _road_width=9.0,
    _round=1,
    _log_file="output_dir/traj_log/cross_double_1_round.npy",
    _round_distance=12,
    _init_road_length=15,
    _over_road_length=30
)
# np.save('output_dir/traj_log/cross_double_3_round', info_round)
for car_id_, traj in enumerate(trajs):
    DistributedMPCIPOPT(traj[0], traj, car_id_)

all_info = DistributedMPCIPOPT.simulate()

# gen_video_from_info(all_info, trajs, draw_nominal=False, _map_info=map_info,
#                     _custom_lim=((-45, 45), (-45, 45))
#                     )
nlp_solve_info = NLP_RESULT_INFO.extract_info_from_info_all(all_info)
PickleSave(nlp_solve_info, "output_dir/solve_info/nlp_solve_info_1")
PickleSave(all_info, "output_dir/solve_info/nlp_all_info_1")
pass
