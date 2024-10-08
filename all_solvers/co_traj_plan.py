import numpy as np
from dynamic_models import dynamic_model
# from dynamic_model import OneDimDynamic
import osqp
from scipy import sparse
import scipy.io
from env import EnvParam
from utilit import suppress_stdout_stderr, JKCalculator
import sys

SDIM = dynamic_model.OneDimDynamic.SDIM
CDIM = dynamic_model.OneDimDynamic.CDIM

U_min = dynamic_model.OneDimDynamic.U_min
U_max = dynamic_model.OneDimDynamic.U_max


def InitSolver(T_num: int, veh_num: int, u_min: float = -3.0, u_max: float = 3.0):
    # init matrixs
    SolverAdmm.T_num = T_num
    SolverAdmm.veh_num = veh_num
    ###########################################
    ## dynamic constrain: B @ (x0) = L @ (S) ##
    ###########################################
    # B
    B = np.zeros((SolverAdmm.T_num * SDIM, SDIM))
    for i in range(SolverAdmm.T_num):
        B[i * SDIM: (i + 1) * SDIM, :] = np.linalg.matrix_power(dynamic_model.OneDimDynamic.Ad, i + 1)
    SolverAdmm.B = B
    # L
    T1 = np.eye(T_num)
    T2 = np.concatenate((np.eye(SDIM), -dynamic_model.OneDimDynamic.Bd), axis=1)
    T3 = np.kron(T1, T2)
    G = np.zeros((T_num * SDIM, T_num * (SDIM + CDIM)))
    for i in range(1, T_num):
        T4 = -dynamic_model.OneDimDynamic.Bd
        for j in range(i, 0, -1):
            T4 = dynamic_model.OneDimDynamic.Ad @ T4
            G[i * SDIM: (i + 1) * SDIM, (j - 1) * (SDIM + CDIM) + SDIM: j * (SDIM + CDIM)] = T4
    SolverAdmm.L = G + T3
    ###########################################
    # state constrain: U_min <= K(S) <= U_max #
    ###########################################
    SolverAdmm.U_min = u_min * np.ones((T_num,))
    SolverAdmm.U_max = u_max * np.ones((T_num,))
    T5 = np.zeros((CDIM, CDIM + SDIM))
    T5[:, SDIM:] = np.eye(CDIM)
    # T5 = np.array([[0, 0, 0, 1]])
    SolverAdmm.K = np.kron(np.eye(T_num), T5)
    ###########################################
    ##### safe constrain: \sim M (S) >= 0 #####
    ############ M needs R ####################
    ###########################################
    SolverAdmm.R = np.kron(np.eye(T_num), np.array([[1, 0, 0, 0]]))
    ##########################################
    ########## (S-S_r)^T Q (S-S_r) ###########
    ##########################################
    Q_ = np.diag([1.0, 1.0, 0.1, 0.1])
    SolverAdmm.Q = np.kron(np.eye(T_num), Q_)


class SolverAdmm:
    # dynamic constrain: b1

    def __init__(self, id: int, x_0: np.ndarray, ref_trace: np.ndarray, rho: float = 0.1, sigma: float = 0.1) -> None:
        self.ID: int = id
        self.rho = rho
        self.sigma = sigma
        self.ref_trace = ref_trace
        # vars
        self.p: np.ndarray = np.zeros((SolverAdmm.T_num * (SolverAdmm.veh_num - 1),))
        self.y: np.ndarray = np.zeros((SolverAdmm.T_num * (SolverAdmm.veh_num - 1),))
        self.z: np.ndarray = np.zeros((SolverAdmm.T_num * (SolverAdmm.veh_num - 1),))
        self.s: np.ndarray = np.zeros((SolverAdmm.T_num * (SolverAdmm.veh_num - 1),))
        self.x: np.ndarray = None
        self.r: np.ndarray = None
        # step-7
        self.M = self._calculateM()
        self.k = self.sigma + 2 * self.rho * (SolverAdmm.veh_num - 1)
        self.P7 = SolverAdmm.Q + (0.5 / self.k) * np.transpose(self.M) @ self.M
        self.q7 = None
        self.A7 = np.concatenate((SolverAdmm.L, SolverAdmm.K), axis=0)
        self.Bx0 = SolverAdmm.B @ x_0[:3]
        self.l7 = np.append(self.Bx0, SolverAdmm.U_min)
        self.u7 = np.append(self.Bx0, SolverAdmm.U_max)

        self.prob = osqp.OSQP()
        self.prob_setup = False

    def step(self, others_y: np.ndarray) -> np.ndarray:
        N_1yi = (SolverAdmm.veh_num - 1) * self.y
        Ayj = others_y.sum(0)
        # for p_k+1
        self.p = self.p + self.rho * (N_1yi - Ayj)
        # for s_k+1
        self.s = self.s + self.sigma * (self.y - self.z)
        # for r_k+1
        self.r = self.rho * (N_1yi + Ayj) + self.sigma * self.z - self.p - self.s
        # for x_k+1
        self.step_for_x()
        # for y_k+1
        self.y = (1 / self.k) * (self.M @ self.x + self.r)
        # for z_k+1
        self.step_for_z()
        return self.y

    def _calculateM(self):
        M = np.zeros(((SolverAdmm.veh_num - 1 + 2) * SolverAdmm.T_num, SolverAdmm.T_num * (SDIM + CDIM)))
        M[(self.ID - 1) * SolverAdmm.T_num: self.ID * SolverAdmm.T_num, :] = -SolverAdmm.R
        M[self.ID * SolverAdmm.T_num: (self.ID + 1) * SolverAdmm.T_num, :] = SolverAdmm.R
        M = M[SolverAdmm.T_num: -SolverAdmm.T_num, :]
        return M

    def step_for_x(self):
        if not self.prob_setup:
            P = sparse.csc_matrix(self.P7)
            q = (0.5 / self.k) * (self.r @ self.M) - self.ref_trace @ SolverAdmm.Q
            A = sparse.csc_matrix(self.A7)
            l = self.l7
            u = self.u7
            self.prob.setup(P, q, A, l, u)
            self.prob_setup = True
        else:
            q = (0.5 / self.k) * (np.transpose(self.r) @ self.M) - self.ref_trace @ SolverAdmm.Q
            self.prob.update(q=q)
        res = self.prob.solve()
        self.x = np.array(res.x)

    def step_for_z(self):
        temp = SolverAdmm.veh_num * (self.s + self.sigma * self.y)
        temp = np.clip(temp, 0, np.inf)
        self.z = (1 / self.sigma) * self.s + self.y - (1 / (SolverAdmm.veh_num * self.sigma)) * temp

    def get_result(self):
        return self.x

'''
class WeightedADMM:
    make_A_D: bool = False
    MatrixA: np.ndarray = None
    MatrixD: np.ndarray = None
    MatrixAD_dict: dict = dict()

    Q_x: np.ndarray = np.diag([1.0, 0.1, 0.1])
    Q_u: np.ndarray = np.diag([1])
    Q_xu: np.ndarray = np.block([[Q_x, np.zeros((Q_x.shape[0], Q_u.shape[1]))],
                                 [np.zeros((Q_u.shape[1], Q_x.shape[0])), Q_u]])

    all_solver: dict = {}

    def makeAD(all_data: dict, graph: str = None) -> None:
        WeightedADMM.make_A_D = True
        if len(all_data) != 10:
            raise NotImplementedError

        if len(all_data) == 10:
            ADmat = scipy.io.loadmat('ADsave/veh_5_5_' + graph + '.mat')
            if graph == 'full':
                WeightedADMM.MatrixA = 0.05 * ADmat['A']
                WeightedADMM.MatrixD = 0.05 * ADmat['D'].diagonal()
            else:
                WeightedADMM.MatrixA = ADmat['A']
                WeightedADMM.MatrixD = ADmat['D'].diagonal()
        main_set = [0, 1, 2, 3, 4]
        merge_set = [5, 6, 7, 8, 9]
        for id in all_data:
            lane = all_data[id][0]
            if lane == 'main':
                WeightedADMM.MatrixAD_dict[id] = main_set.pop(0)
            if lane == 'merge':
                WeightedADMM.MatrixAD_dict[id] = merge_set.pop(0)
        return

    def __init__(self, id: int, veh_num: int, one_data: list) -> None:
        if not WeightedADMM.make_A_D:
            print("Uninitialize A and D")
            raise ValueError

        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        # base value
        self.lane = lane
        self.veh_num = veh_num
        self.T_nums = int((trace.shape[0] - (SDIM + CDIM)) / (SDIM + CDIM))  # trace include init state
        WeightedADMM.all_solver[id] = self
        self.id = id
        self.to = to
        # matrix
        self.ref_trace: np.ndarray = trace[CDIM + SDIM:]
        self.x0 = trace[:SDIM]
        self.b_i: np.ndarray = self.Generateb_i(one_data)
        self.A_i: np.ndarray = self.GenerateA_i(one_data)
        # variable
        self.x: np.ndarray = np.zeros((self.T_nums * (SDIM + CDIM),))
        self.y_self: np.ndarray = np.zeros((veh_num * self.T_nums,))
        self.y_all: np.ndarray = np.zeros((veh_num, veh_num * self.T_nums))
        self.p: np.ndarray = np.zeros((veh_num * self.T_nums,))
        self.v: np.ndarray = -self.b_i
        # hyper param
        self.a_j: np.ndarray = WeightedADMM.MatrixA[WeightedADMM.MatrixAD_dict[self.id]]
        self.d_ii: float = WeightedADMM.MatrixD[WeightedADMM.MatrixAD_dict[self.id]]
        # solverx
        self.SolveX = self.SolveX_Closure()

    def Generateb_i(self, one_data: list) -> np.ndarray:
        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        b_i = np.zeros((self.T_nums * self.veh_num))
        if iop is not None:
            b_i[(self.id - 1) * self.T_nums: (self.id - 1) * self.T_nums + to] = EnvParam.Dsafe
        if iof is not None:
            b_i[(self.id - 1) * self.T_nums + to: self.id * self.T_nums] = EnvParam.Dsafe
        return b_i

    def GenerateA_i(self, one_data: list) -> np.ndarray:
        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        A_i = np.zeros((self.T_nums * self.veh_num, self.T_nums * (CDIM + SDIM)))
        temp = np.kron(np.eye(self.T_nums), np.array((1, 0, 0, 0)))
        if iop is not None:
            A_i[(self.id - 1) * self.T_nums: (self.id - 1) * self.T_nums + to] = -temp[: to]
        if iof is not None:
            A_i[(self.id - 1) * self.T_nums + to: self.id * self.T_nums] = -temp[to:]
        if oiop is not None:
            A_i[(oiop[0] - 1) * self.T_nums: (oiop[0] - 1) * self.T_nums + oiop[1]] = temp[: oiop[1]]
        if oiof is not None:
            A_i[(oiof[0] - 1) * self.T_nums + oiof[1]:               oiof[0] * self.T_nums] = temp[oiof[1]:]
        return A_i

    # @staticmethod
    # def generate_y_all(veh_num: int, y_shape: tuple) -> np.ndarray:
    # result = np.zeros(veh_num)
    # for i in range(veh_num):
    # id = i+1
    # result[id] = np.zeros(y_shape)
    # return result

    def _UpdateY(self) -> None:
        for id in WeightedADMM.all_solver:
            self.y_all[id - 1] = WeightedADMM.all_solver[id].y_self.copy()

    def SolveP1(self) -> None:
        # for v
        self.v = self.d_ii * self.y_self + self.a_j @ self.y_all - self.b_i - self.p
        # qp for x, t
        t = self.x.copy()
        self.x, _ = self.SolveX()
        # print(np.linalg.norm(t - self.x))
        # for y
        # t = np.clip(self.A_i @ self.x + self.v, -np.inf, 0) / (2*self.d_ii)
        # print(np.linalg.norm(t - self.y_self))
        self.y_self = np.clip(self.A_i @ self.x + self.v, -np.inf, 0) / (2 * self.d_ii)

    def SolveP2(self) -> None:
        # communicate
        self._UpdateY()
        # for p
        self.p = self.p + self.d_ii * self.y_self - self.a_j @ self.y_all

    def SolveX_Closure(self):
        Big_Q_ux = np.kron(np.eye(self.T_nums), WeightedADMM.Q_xu)
        Big_Q_ux[-(CDIM + SDIM):, -(CDIM + SDIM):] = WeightedADMM.Q_xu * 10
        t_dim = self.veh_num * self.T_nums
        J = np.block([[Big_Q_ux, np.zeros((Big_Q_ux.shape[0], t_dim))],
                      [np.zeros((t_dim, Big_Q_ux.shape[1])), np.zeros((t_dim, t_dim))]])
        K = np.block([-2 * self.ref_trace @ Big_Q_ux, np.zeros(t_dim)])
        L = np.block([self.A_i, -np.eye(t_dim)])

        P = 2 * (J + (1 / (4 * self.d_ii)) * L.transpose() @ L)
        q_fun = lambda K, L, v, d_ii: K + (1 / (2 * d_ii)) * v @ L

        C_U_A = np.block([np.kron(np.eye(self.T_nums), np.array([0, 0, 0, 1])), np.zeros((self.T_nums, t_dim))])
        C_U_l = U_min * np.ones(self.T_nums)
        C_U_u = U_max * np.ones(self.T_nums)

        T1 = np.eye(self.T_nums)
        T2 = np.concatenate((np.eye(SDIM), -dynamic_model.OneDimDynamic.Bd), axis=1)
        T3 = np.kron(T1, T2)
        G = np.zeros((self.T_nums * SDIM, self.T_nums * (SDIM + CDIM)))
        for i in range(1, self.T_nums):
            T4 = -dynamic_model.OneDimDynamic.Bd
            for j in range(i, 0, -1):
                T4 = dynamic_model.OneDimDynamic.Ad @ T4
                G[i * SDIM: (i + 1) * SDIM, (j - 1) * (SDIM + CDIM) + SDIM: j * (SDIM + CDIM)] = T4
        B = np.zeros((self.T_nums * SDIM, SDIM))
        for i in range(self.T_nums):
            B[i * SDIM: (i + 1) * SDIM, :] = np.linalg.matrix_power(dynamic_model.OneDimDynamic.Ad, i + 1)
        C_D_A = np.block([G + T3, np.zeros((self.T_nums * SDIM, t_dim))])
        C_D_l = B @ self.x0
        C_D_u = C_D_l

        C_X_A = np.zeros((2, self.T_nums * (CDIM + SDIM) + t_dim))
        C_X_A[0, self.to * (CDIM + SDIM)] = 1
        C_X_A[1, (self.to + 1) * (CDIM + SDIM)] = 1
        C_X_l = np.array([-np.inf, 0])
        C_X_u = np.array([0, +np.inf])

        C_T_A = np.block([np.zeros((t_dim, self.T_nums * (CDIM + SDIM))), np.eye(t_dim)])
        C_T_l = np.zeros((t_dim,))
        C_T_u = np.ones((t_dim,)) * np.inf

        A = np.block([[C_U_A],
                      [C_D_A],
                      [C_X_A],
                      [C_T_A]])
        l = np.block([C_U_l, C_D_l, C_X_l, C_T_l])
        u = np.block([C_U_u, C_D_u, C_X_u, C_T_u])

        q = q_fun(K, L, self.v, self.d_ii)
        prob = osqp.OSQP()

        P = sparse.csc_matrix(P)
        A = sparse.csc_matrix(A)
        with suppress_stdout_stderr():
            prob.setup(P, q, A, l, u)

        def SolveX():
            nonlocal q_fun, prob, t_dim, K, L

            q = q_fun(K, L, self.v, self.d_ii)
            prob.update(q=q)
            with suppress_stdout_stderr():
                res = prob.solve()
            res = np.array(res.x)
            # print('id', self.id)
            return res[: self.T_nums * (SDIM + CDIM)], res[-t_dim:]

        return SolveX
'''


class FullADMM:
    rho = 0.1

    Q_x: np.ndarray = np.diag([5.5, 0.1, 0.1])
    Q_u: np.ndarray = np.diag([0.1])
    Q_xu: np.ndarray = np.block([[Q_x, np.zeros((Q_x.shape[0], Q_u.shape[1]))],
                                 [np.zeros((Q_u.shape[1], Q_x.shape[0])), Q_u]])

    all_solver: dict = {}

    def __init__(self, id: int, veh_num: int, one_data: list, X_constrain: bool = True) -> None:

        self.X_constrain = X_constrain

        FullADMM.all_solver[id] = self
        # base value
        self.id = id
        self.veh_num = veh_num
        self.lane, self.t0, self.tf, self.to, self.x0, self.xf, self.iop, self.iof, self.oiop, self.oiof, self.trace = one_data
        self.d_i = veh_num - 1
        # others
        self.T_nums: int = int((self.trace.shape[0] - (SDIM + CDIM)) / (SDIM + CDIM))  # trace include init state
        self.x0: np.ndarray = self.trace[:SDIM]
        self.ref_trace: np.ndarray = self.trace[CDIM + SDIM:]
        if self.X_constrain:
            self.b_i: np.ndarray = self._Generateb_i(one_data)
            self.A_i: np.ndarray = self._GenerateA_i(one_data)
        else:
            self.b_i: np.ndarray = self._Generateb_i_new(one_data)
            self.A_i: np.ndarray = self._GenerateA_i_new(one_data)
        # variable
        self.x: np.ndarray = np.zeros((self.T_nums * (SDIM + CDIM),))
        self.y_self: np.ndarray = np.zeros((veh_num * self.T_nums,))
        self.y_all: np.ndarray = np.zeros((veh_num, veh_num * self.T_nums))
        self.p: np.ndarray = np.zeros((veh_num * self.T_nums,))
        self.v: np.ndarray = np.zeros((veh_num * self.T_nums,))
        # solverx
        self.SolveX = self.SolveX_Closure()

    def _Generateb_i_new(self, one_data: list) -> np.ndarray:
        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        b_i = np.zeros((self.T_nums * self.veh_num))
        if iop is not None:
            b_i[(self.id - 1) * self.T_nums: self.id * self.T_nums] = EnvParam.Dsafe
        return b_i

    def _GenerateA_i_new(self, one_data: list) -> np.ndarray:
        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        A_i = np.zeros((self.T_nums * self.veh_num, self.T_nums * (CDIM + SDIM)))
        temp = np.kron(np.eye(self.T_nums), np.array((1, 0, 0, 0)))
        if iop is not None:
            A_i[(self.id - 1) * self.T_nums: self.id * self.T_nums] = -temp
        if oiop is not None:
            A_i[(oiop[0] - 1) * self.T_nums: oiop[0] * self.T_nums] = temp
        return A_i

    def _Generateb_i(self, one_data: list) -> np.ndarray:
        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        b_i = np.zeros((self.T_nums * self.veh_num))
        if iop is not None:
            b_i[(self.id - 1) * self.T_nums: (self.id - 1) * self.T_nums + to] = EnvParam.Dsafe
        if iof is not None:
            b_i[(self.id - 1) * self.T_nums + to: self.id * self.T_nums] = EnvParam.Dsafe
        return b_i

    def _GenerateA_i(self, one_data: list) -> np.ndarray:
        lane, t0, tf, to, x0, xf, iop, iof, oiop, oiof, trace = one_data
        A_i = np.zeros((self.T_nums * self.veh_num, self.T_nums * (CDIM + SDIM)))
        temp = np.kron(np.eye(self.T_nums), np.array((1, 0, 0, 0)))
        if iop is not None:
            A_i[(self.id - 1) * self.T_nums: (self.id - 1) * self.T_nums + to] = -temp[: to]
        if iof is not None:
            A_i[(self.id - 1) * self.T_nums + to: self.id * self.T_nums] = -temp[to:]
        if oiop is not None:
            A_i[(oiop[0] - 1) * self.T_nums: (oiop[0] - 1) * self.T_nums + oiop[1]] = temp[: oiop[1]]
        if oiof is not None:
            A_i[(oiof[0] - 1) * self.T_nums + oiof[1]:               oiof[0] * self.T_nums] = temp[oiof[1]:]
        return A_i

    def UpdateY(self) -> None:
        for id in FullADMM.all_solver:
            self.y_all[id - 1] = FullADMM.all_solver[id].y_self.copy()

    def Solve(self) -> None:
        # communicate
        # self._UpdateY()
        # for p
        self.p = self.p + FullADMM.rho * ((self.d_i + 1) * self.y_self - sum(self.y_all))
        # for v
        self.v = FullADMM.rho * ((self.d_i - 1) * self.y_self + sum(self.y_all)) - self.b_i - self.p
        # qp for x, t
        self.x, _ = self.SolveX()
        # for y
        self.y_self = np.clip(self.A_i @ self.x + self.v, -np.inf, 0) / (2 * self.rho * self.d_i)

    def SolveX_Closure(self) -> tuple:
        # calculate P
        Big_Q_ux = np.kron(np.eye(self.T_nums), FullADMM.Q_xu)
        Big_Q_ux[-(CDIM + SDIM):, -(CDIM + SDIM):] = FullADMM.Q_xu * 10
        t_dim = self.veh_num * self.T_nums
        J = np.block([[Big_Q_ux, np.zeros((Big_Q_ux.shape[0], t_dim))],
                      [np.zeros((t_dim, Big_Q_ux.shape[1])), np.zeros((t_dim, t_dim))]])
        K = np.block([-2 * self.ref_trace @ Big_Q_ux, np.zeros(t_dim)])
        L = np.block([self.A_i, -np.eye(t_dim)])
        P = 2 * (J + (1 / (4 * self.d_i * self.rho)) * L.transpose() @ L)

        # q change every time
        q_fun = lambda K, L, v: K + (0.5 / (self.d_i * self.rho)) * v @ L

        # input constrain
        C_U_A = np.block([np.kron(np.eye(self.T_nums), np.array([0, 0, 0, 1])), np.zeros((self.T_nums, t_dim))])
        C_U_l = U_min * np.ones(self.T_nums)
        C_U_u = U_max * np.ones(self.T_nums)

        # dynamic constrain
        T1 = np.eye(self.T_nums)
        T2 = np.concatenate((np.eye(SDIM), -dynamic_model.OneDimDynamic.Bd), axis=1)
        T3 = np.kron(T1, T2)
        G = np.zeros((self.T_nums * SDIM, self.T_nums * (SDIM + CDIM)))
        for i in range(1, self.T_nums):
            T4 = -dynamic_model.OneDimDynamic.Bd
            for j in range(i, 0, -1):
                T4 = dynamic_model.OneDimDynamic.Ad @ T4
                G[i * SDIM: (i + 1) * SDIM, (j - 1) * (SDIM + CDIM) + SDIM: j * (SDIM + CDIM)] = T4
        B = np.zeros((self.T_nums * SDIM, SDIM))
        for i in range(self.T_nums):
            B[i * SDIM: (i + 1) * SDIM, :] = np.linalg.matrix_power(dynamic_model.OneDimDynamic.Ad, i + 1)
        C_D_A = np.block([G + T3, np.zeros((self.T_nums * SDIM, t_dim))])
        C_D_l = B @ self.x0
        C_D_u = C_D_l

        # state constain
        C_X_A = np.zeros((2, self.T_nums * (CDIM + SDIM) + t_dim))
        C_X_A[0, self.to * (CDIM + SDIM)] = 1
        C_X_A[1, (self.to + 1) * (CDIM + SDIM)] = 1
        C_X_l = np.array([-np.inf, 0])
        C_X_u = np.array([0, +np.inf])

        # constrain of t in cone
        C_T_A = np.block([np.zeros((t_dim, self.T_nums * (CDIM + SDIM))), np.eye(t_dim)])
        C_T_l = np.zeros((t_dim,))
        C_T_u = np.ones((t_dim,)) * np.inf

        if self.X_constrain:
            A = np.block([[C_U_A],
                          [C_D_A],
                          [C_X_A],
                          [C_T_A]])
            l = np.block([C_U_l, C_D_l, C_X_l, C_T_l])
            u = np.block([C_U_u, C_D_u, C_X_u, C_T_u])
        else:
            A = np.block([[C_U_A],
                          [C_D_A],
                          [C_T_A]])
            l = np.block([C_U_l, C_D_l, C_T_l])
            u = np.block([C_U_u, C_D_u, C_T_u])

        q = q_fun(K, L, self.v)
        prob = osqp.OSQP()

        P = sparse.csc_matrix(P)
        A = sparse.csc_matrix(A)
        with suppress_stdout_stderr():
            prob.setup(P, q, A, l, u)

        def SolveX():
            nonlocal q_fun, prob, t_dim, K, L

            q = q_fun(K, L, self.v)
            prob.update(q=q)
            with suppress_stdout_stderr():
                res = prob.solve()
            res = np.array(res.x)
            # print('id', self.id)
            return res[: self.T_nums * (SDIM + CDIM)], res[-t_dim:]

        return SolveX

    def CollectTraces() -> dict[int: tuple[str, np.ndarray]]:
        '''
        return:
            {id: (
                lane, trace
            )}
        '''
        assert len(FullADMM.all_solver) != 0
        all_trace = {}
        for id in FullADMM.all_solver:
            solver = FullADMM.all_solver[id]
            trace = solver.x.reshape((-1, 4))[:, 0: 3]
            lane = solver.lane
            id = solver.id
            all_trace[id] = (lane, trace)
        return all_trace
