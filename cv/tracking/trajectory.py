import numpy as np


def split_track_improved(coords, max_gap=10):
    segments = []
    start_idx = None
    gap_count = 0  # 记录连续无效帧

    for i, p in enumerate(coords):
        # 严格判定：不仅不是 None，而且元组里的坐标不能是 NaN
        is_valid = p is not None and not np.isnan(p[0])

        if is_valid:
            if start_idx is None:
                start_idx = i
            gap_count = 0  # 只要遇到好点，计数器清零
        else:
            if start_idx is not None:
                gap_count += 1
                if gap_count > max_gap:
                    # 关键计算：结束点应该是最后一个有效点，即 i - gap_count
                    segments.append((start_idx, i - gap_count))
                    start_idx = None
                    gap_count = 0

    # 处理收尾工作
    if start_idx is not None:
        # 注意：这里的结束点也应该是最后一个有效点，而不是 len(coords)-1
        # 寻找列表末尾最后一个有效点
        last_valid = start_idx
        for j in range(len(coords) - 1, start_idx - 1, -1):
            if coords[j] is not None and not np.isnan(coords[j][0]):
                last_valid = j
                break
        segments.append((start_idx, last_valid))

    return segments
def remove_outliers_improved(coords, v_threshold=35, a_threshold=20):
    """
    基于速度和加速度连续性的剔除算法
    v_threshold: 相邻帧最大位移(像素)
    a_threshold: 允许的最大速度变化(加速度控制)
    """
    n = len(coords)
    # 第一次遍历：基于绝对速度(位移)剔除
    for i in range(1, n - 1):
        if coords[i] is None or coords[i-1] is None:
            continue
        
        # 计算当前帧相对于前一帧的位移
        dx = abs(coords[i][0] - coords[i-1][0])
        dy = abs(coords[i][1] - coords[i-1][1])
        
        # 只要任意一个方向跳变过大，就判定为异常
        if dx > v_threshold or dy > v_threshold:
            coords[i] = None
            
    # 第二次遍历：基于加速度(轨迹平滑度)剔除
    for i in range(1, n - 1):
        if coords[i-1] is None or coords[i] is None or coords[i+1] is None:
            continue
            
        # 计算 v1 (i-1 到 i) 和 v2 (i 到 i+1)
        v1_y = coords[i][1] - coords[i-1][1]
        v2_y = coords[i+1][1] - coords[i][1]
        
        # 如果 y 方向速度突然反向且不在地面附近（非反弹），通常是误检
        # 这种逻辑更符合网球抛物线模型
        if abs(v2_y - v1_y) > a_threshold:
            coords[i] = None
def fmt(p):
    """
    格式化坐标点：将 [x, y] 转换为 (x, y) 字符串，如果是 None 则返回 "None"
    """
    if p is not None and len(p) >= 2:
        return f"({p[0]:.1f}, {p[1]:.1f})"
    return "None"


def nan_helper(y):
    """Helper to handle indices and logical indices of NaNs.

    Input:
        - y, 1d numpy array with possible NaNs
    Output:
        - nans, logical indices of NaNs
        - index, a function, with signature indices= index(logical_indices),
          to convert logical indices of NaNs to 'equivalent' indices
    Example:
        >>> # linear interpolation of NaNs
        >>> nans, x= nan_helper(y)
        >>> y[nans]= np.interp(x(nans), x(~nans), y[~nans])
    """
    return np.isnan(y), lambda z: z.nonzero()[0]


def interpolation(coords):
    coords = coords.copy()
    x, y = [x[0] if x is not None else np.nan for x in coords], [x[1] if x is not None else np.nan for x in coords]

    xxx = np.array(x)  # x coords
    yyy = np.array(y)  # y coords

    nons, yy = nan_helper(xxx)
    xxx[nons] = np.interp(yy(nons), yy(~nons), xxx[~nons])
    nans, xx = nan_helper(yyy)
    yyy[nans] = np.interp(xx(nans), xx(~nans), yyy[~nans])

    newCoords = [*zip(xxx, yyy)]

    return newCoords


def diff_xy(coords):
    coords = coords.copy()
    diff_list = []
    for i in range(0, len(coords) - 1):
        if coords[i] is not None and coords[i + 1] is not None:
            point1 = coords[i]
            point2 = coords[i + 1]
            diff = [abs(point2[0] - point1[0]), abs(point2[1] - point1[1])]
            diff_list.append(diff)
        else:
            diff_list.append(None)

    xx, yy = np.array([x[0] if x is not None else np.nan for x in diff_list]), np.array(
        [x[1] if x is not None else np.nan for x in diff_list])

    return xx, yy

