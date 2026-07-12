import os
import cv2
import torch
import numpy as np
import argparse
import pandas as pd
from tqdm import tqdm
from collections import deque
from ultralytics import YOLO

from cv.analytics.player_distance import calculate_player_distances
from cv.analytics.rally import _build_rally_analysis
from cv.analytics.shot_speed import calculate_shot_speeds_true_meters
from cv.config import CV_ROOT, INPUT_DIR, OUTPUT_DIR, WEIGHTS_DIR
from cv.court import CourtReference
from cv.court.keypoints import get_matrix_from_model
from cv.events.hit_detection import standalone_get_ball_shot_frames
from cv.events.in_out import evaluate_bounces_in_out
from cv.events.net_hit.detector import NetHitConfig, detect_net_hits, make_horizontal_net_line
from cv.events.shot_classifier import ShotClassifier
from cv.io.json import export_analysis_to_separated_json
from cv.io.video import save_video
from cv.models.court_detection import BallTrackerNet
from cv.tracking.ball import BallTrackerManager
from cv.tracking.bounce import BounceDetectorManager
from cv.tracking.person import PersonTrackerManager
from cv.visualization.minimap import render_with_minimap
from cv.visualization.overlays import draw_court_dots, draw_shot_announcements

current_dir = str(CV_ROOT)


# ==========================================
# 🚀 新增：YOLO 包装器与场地适配器 (解耦底层逻辑)
# ==========================================
class YoloDetectionWrapper:
    """包装原版 YOLO，提供 PersonTrackerManager 需要的 _detect 接口"""

    def __init__(self, model_path, device):
        self.model = YOLO(model_path)
        self.model.to(device)

    def _detect(self, frame, person_min_score=0.5):
        # class 0 是 person
        results = self.model(frame, classes=[0], conf=person_min_score, verbose=False)
        boxes, probs = [], []
        for r in results:
            for box in r.boxes:
                boxes.append(box.xyxy[0].cpu().numpy().tolist())
                probs.append(float(box.conf[0]))
        return boxes, probs


class DummyCourtDetector:
    """包装场地数据，提供给追踪器进行物理空间转换"""

    def __init__(self, court_ref):
        self.court_reference = court_ref
        self.court_warp_matrix = []



def main():
    parser = argparse.ArgumentParser(description="网球视频分析推理脚本")
    parser.add_argument("--input_video_path", type=str, default=None,
                        help="输入视频路径（默认：data/input/long5.mp4）")
    parser.add_argument("--ball_model_path", type=str, default=None,
                        help="球检测模型路径（默认：models/weights/model_best.pt）")
    parser.add_argument("--player_model_path", type=str, default=None,
                        help="球员检测模型路径（默认：models/weights/yolov8x.pt）")
    parser.add_argument("--court_model_path", type=str, default=None,
                        help="球场检测模型路径（默认：models/weights/model_tennis_court_det.pt）")
    parser.add_argument("--output_video_path", type=str, default=None,
                        help="输出视频路径（默认：data/output/<input>_processed.mp4）")
    args = parser.parse_args()

    # 解析模型路径（默认相对于脚本目录）
    weights_dir = str(WEIGHTS_DIR)
    input_dir = str(INPUT_DIR)
    output_dir = str(OUTPUT_DIR)

    if args.input_video_path is None:
        args.input_video_path = os.path.join(input_dir, "long5.mp4")
    elif not os.path.isabs(args.input_video_path):
        args.input_video_path = os.path.join(current_dir, args.input_video_path)

    if args.ball_model_path is None:
        args.ball_model_path = os.path.join(weights_dir, "model_best.pt")
    elif not os.path.isabs(args.ball_model_path):
        args.ball_model_path = os.path.join(current_dir, args.ball_model_path)

    if args.player_model_path is None:
        args.player_model_path = os.path.join(weights_dir, "yolov8x.pt")
    elif not os.path.isabs(args.player_model_path):
        args.player_model_path = os.path.join(current_dir, args.player_model_path)

    if args.court_model_path is None:
        args.court_model_path = os.path.join(weights_dir, "model_tennis_court_det.pt")
    elif not os.path.isabs(args.court_model_path):
        args.court_model_path = os.path.join(current_dir, args.court_model_path)

    if args.output_video_path is None:
        # 默认：输入文件名 + "_processed"，与输入视频同目录
        base = os.path.splitext(os.path.basename(args.input_video_path))[0]
        ext = os.path.splitext(args.input_video_path)[1]
        args.output_video_path = os.path.join(output_dir, f"{base}_processed{ext}")
    elif not os.path.isabs(args.output_video_path):
        args.output_video_path = os.path.join(current_dir, args.output_video_path)

    # 确保输出目录存在
    output_dir_path = os.path.dirname(args.output_video_path)
    if output_dir_path and not os.path.exists(output_dir_path):
        os.makedirs(output_dir_path)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"[*] 使用计算设备: {device}")
    print(f"[*] 输入视频: {args.input_video_path}")
    print(f"[*] 输出视频: {args.output_video_path}")

    # 检查必要的文件是否存在
    for name, path in [("输入视频", args.input_video_path),
                       ("球模型", args.ball_model_path),
                       ("球员模型", args.player_model_path),
                       ("球场模型", args.court_model_path)]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{name} 不存在: {path}\n请检查路径是否正确")

    # 获取视频元数据
    cap = cv2.VideoCapture(args.input_video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {args.input_video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 1. 初始化场地参照模型 (提前实例化，为了给追踪器提供物理掩码)
    court_ref_instance = CourtReference()
    court_ref_instance.build_court_reference()
    dummy_court = DummyCourtDetector(court_ref_instance)

    # 2. 初始化神经网络模型
    court_model = BallTrackerNet(out_channels=15).to(device)
    court_model.load_state_dict(torch.load(args.court_model_path, map_location=device,weights_only=True))
    court_model.eval()

    ball_tracker = BallTrackerManager(model_path=args.ball_model_path, device=device)

    # 💥 3. 初始化全新的人员追踪引擎
    yolo_detector = YoloDetectionWrapper(model_path=args.player_model_path, device=device)
    person_tracker = PersonTrackerManager(detection_model=yolo_detector)

    # ==========================================
    # 🏃‍♂️ 趟一 (Pass 1): 流式扫描视频，榨取坐标数据
    # ==========================================
    print("\n>>> [1/4] 趟一：流式扫描视频，提取多模态坐标与场地角色识别...")

    court_points_all = []
    court_matrices_all = []
    player_detections = {}
    player_detections_court = {}  # 球员场地坐标(米)
    ball_detections_court = {}    # 球场地坐标(米)
    raw_coords = []

    tracknet_buffer = deque(maxlen=3)
    pbar = tqdm(total=total_frames, desc="流式特征榨取")
    frame_idx = 0

    # 记录上一个靠谱的矩阵，防止追踪器因丢帧而崩溃
    last_good_matrix = np.eye(3)

    # DeepSort track_id → player_id (1=近端/首帧下半场, 2=远端/首帧上半场)
    # 首次见到某个 track 时按位置分配，之后 ID 跟随 track 而非位置
    track_id_to_player_id = {}

    while True:
        ret, frame = cap.read()
        if not ret: break

        # 1. 抽场地坐标
        matrix, pts = get_matrix_from_model(frame, court_model, device)
        court_points_all.append(pts)
        court_matrices_all.append(matrix)

        # 维护场地状态，供给追踪器使用
        if matrix is not None:
            last_good_matrix = matrix
        dummy_court.court_warp_matrix.append(last_good_matrix)

        # 2. 球员追踪：ID 固化跟随 track，换边后 ID 不变
        tracks = person_tracker.update(frame, dummy_court)
        frame_player_dict = {}

        # 第一遍：为首次出现的 track 分配 player_id（基于当前位置，且不重复占用）
        # 只统计当前帧仍活跃的 track 所占用的 ID：镜头切回时旧 track 已老化删除，
        # ID 自动释放，新 track 能重新按位置绑定，避免切回后检测框消失
        active_confirmed = {t.track_id for t in tracks if t.is_confirmed()}
        already_used = {pid for tid, pid in track_id_to_player_id.items()
                        if tid in active_confirmed}
        for track in tracks:
            if not track.is_confirmed():
                continue
            tid = track.track_id
            if tid in track_id_to_player_id:
                continue
            role = track.det_class
            if role == "bottom_player":
                candidate = 1
            elif role == "top_player":
                candidate = 2
            else:
                continue
            if candidate not in already_used:
                track_id_to_player_id[tid] = candidate
                already_used.add(candidate)

        # 第二遍：用已固化的映射填充本帧数据
        for track in tracks:
            if not track.is_confirmed():
                continue
            player_id = track_id_to_player_id.get(track.track_id)
            if player_id is not None:
                frame_player_dict[player_id] = [float(x) for x in track.to_ltrb()]

        # 存入主字典
        player_detections[frame_idx] = frame_player_dict

        # 转换球员坐标到场地米坐标
        player_court_dict = {}
        for p_id, bbox in frame_player_dict.items():
            feet_pixel = [(bbox[0] + bbox[2]) / 2.0, bbox[3]]
            try:
                H_inv = np.linalg.inv(last_good_matrix)
                pt = np.array([[feet_pixel[0]], [feet_pixel[1]], [1.0]])
                res = np.dot(H_inv, pt)
                canvas_x, canvas_y = res[0, 0] / res[2, 0], res[1, 0] / res[2, 0]
                real_x = (canvas_x - 120.0) / 30.0
                real_y = (canvas_y - 150.0) / 30.0
                player_court_dict[p_id] = [round(float(real_x), 2), round(float(real_y), 2)]
            except:
                player_court_dict[p_id] = None
        player_detections_court[frame_idx] = player_court_dict

        # 3. 抽网球坐标
        tracknet_buffer.append(frame.copy())
        ball_xy = None
        if len(tracknet_buffer) == 3:
            ball_xy = ball_tracker.runner.infer_model_3_frames(
                tracknet_buffer[0], tracknet_buffer[1], tracknet_buffer[2]
            )
        raw_coords.append(ball_xy)

        # 转换球坐标到场地米坐标
        if ball_xy is not None:
            try:
                H_inv = np.linalg.inv(last_good_matrix)
                pt = np.array([[ball_xy[0]], [ball_xy[1]], [1.0]])
                res = np.dot(H_inv, pt)
                canvas_x, canvas_y = res[0, 0] / res[2, 0], res[1, 0] / res[2, 0]
                real_x = (canvas_x - 120.0) / 30.0
                real_y = (canvas_y - 150.0) / 30.0
                ball_detections_court[frame_idx] = [round(float(real_x), 2), round(float(real_y), 2)]
            except:
                ball_detections_court[frame_idx] = None

        frame_idx += 1
        pbar.update(1)

    cap.release()
    pbar.close()

    # ==========================================
    # 🧠 中场: 全量业务逻辑运算
    # ==========================================
    print("\n>>> [2/4] 运算中心：执行聚类与动作分类...")

    # 旧的场内过滤 (choose_and_filter_players) 已被移除！
    # 因为现在的 player_detections 里只有纯正的 bottom_player 和 top_player。

    # 1. 网球轨迹平滑与插值
    final_coords = ball_tracker.process_trajectory(raw_coords, enable_smoothing=False)

    # 2. 落点突变分析
    bounce_detector = BounceDetectorManager(score_thresh=15.0)
    raw_bounces, _, _ = bounce_detector.detect(final_coords)
    enhanced_bounces = bounce_detector.enhance_subpixel(final_coords, raw_bounces)

    # 3. 击球点分析预处理
    adapted_for_detector = []
    adapted_for_classifier = {}
    for i, p in enumerate(final_coords):
        if p is not None and not np.isnan(p).any():
            cx, cy = float(p[0]), float(p[1])
            adapted_for_detector.append({1: [cx - 5, cy - 5, cx + 5, cy + 5]})
            adapted_for_classifier[i] = {1: [cx, cy]}
        else:
            adapted_for_detector.append({})
            adapted_for_classifier[i] = {}

    # 4. 执行核心加权算法
    ball_shot_frames, candidate_frames,hit_player = standalone_get_ball_shot_frames(adapted_for_detector, player_detections,
                                                                         frame_height)
    shot_frames_set = set(ball_shot_frames)
    candidate_frames_set = set(candidate_frames)

    # 5. 互斥抑制窗口清洗落地框
    SUPPRESSION_WINDOW = 6
    final_valid_bounces = []
    for b in enhanced_bounces:
        b_frame = b.get('frame')
        if b_frame is not None and not any(abs(b_frame - hf) <= SUPPRESSION_WINDOW for hf in shot_frames_set):
            final_valid_bounces.append(b)

    final_valid_bounces = evaluate_bounces_in_out(
        bounces=final_valid_bounces,
        court_matrices_all=court_matrices_all,
        match_type="singles",  # 如果你分析的是单打比赛
        padding_x=120,
        padding_y=150,
        ppm=30
    )

    # 6. 透视场提取与动作分类
    court_lines_pixel_y = {}
    player_pixel_bottom = {}

    for i in range(frame_idx):
        pts = court_points_all[i]
        valid_y = [p[1] for p in pts if p is not None and p[1] is not None]
        if valid_y:
            top_y, bot_y = min(valid_y), max(valid_y)
            net_y = int(top_y + (bot_y - top_y) * 0.35)
            court_lines_pixel_y[i] = {'net_y': net_y, 'top_baseline_y': int(top_y), 'bottom_baseline_y': int(bot_y)}
        else:
            court_lines_pixel_y[i] = court_lines_pixel_y.get(i - 1,
                                                             {'net_y': int(frame_height * 0.45), 'top_baseline_y': 200,
                                                              'bottom_baseline_y': 900})

        p_frame = player_detections.get(i, {})
        player_pixel_bottom[i] = {p_id: [(b[0] + b[2]) / 2, b[3]] for p_id, b in p_frame.items() if b is not None}

    # 7. 落网检测
    median_net_y = None
    if court_lines_pixel_y:
        net_ys = [v['net_y'] for v in court_lines_pixel_y.values() if 'net_y' in v]
        if net_ys:
            median_net_y = int(np.median(net_ys))

    net_hit_events = []
    if median_net_y is not None:
        net_config = NetHitConfig(
            net_line=make_horizontal_net_line(median_net_y, frame_width),
            fps=fps,
            near_net_px=35.0,
            min_confidence=0.55
        )
        net_hit_events = detect_net_hits(final_coords, net_config)

    # 8. 动作分类

    shot_classifier = ShotClassifier()
    shot_classifications = shot_classifier.classify_shots(
        player_pixel_detections=player_pixel_bottom,
        ball_pixel_detections=adapted_for_classifier,
        ball_shot_frames=ball_shot_frames,
        frame_height=frame_height,
        court_lines_pixel_y=court_lines_pixel_y
    )

    print(f"    - 算法结算完毕: 确认击球数 {len(ball_shot_frames)}, 有效落点数 {len(final_valid_bounces)}, 落网数 {len(net_hit_events)}")

    # ==========================================
    # 🎨 趟二 (Pass 2): 流式渲染，照抄答案输出
    # ==========================================
    # 💥 改动 1：把算出来的跑动距离保存到变量里
    shot_speed = calculate_shot_speeds_true_meters(
        shot_classifications=shot_classifications,
        bounces=final_valid_bounces,
        player_detections=player_detections,
        court_matrices_all=court_matrices_all,
        fps=fps,
        min_speed_kmh=30.0  # 设为 30，职业比赛低于 30 的大概率是轻触或者误报
    )
    player_distances = calculate_player_distances(player_detections, court_matrices_all)
    rally_analysis = _build_rally_analysis(
        fps=fps,
        total_frames=frame_idx,
        ball_shot_frames=ball_shot_frames,
        bounce_frames=[b.get("frame") for b in final_valid_bounces],
        shot_classifications=shot_classifications,
        shot_speeds=shot_speed,
        cumulative_distances=player_distances,
        player_detections=player_detections,
        player_detections_court=player_detections_court,
        ball_detections=adapted_for_detector,
        ball_detections_court=ball_detections_court,
        bounces=final_valid_bounces,
        court_matrices=court_matrices_all
    )
    print(f"    - 回合切分完成: {rally_analysis['rally_count']} rallies")

    print("\n>>> [4/4] 趟二：重开视频，流式写入极客 UI...")

    ball_pos_list = [x.get(1, []) for x in adapted_for_detector]
    df_trace = pd.DataFrame(ball_pos_list, columns=['x1', 'y1', 'x2', 'y2'])
    df_trace['mid_y'] = (df_trace['y1'] + df_trace['y2']) / 2
    df_trace['prev_3'] = df_trace['mid_y'].rolling(window=3).mean().shift(1)
    df_trace['next_3'] = df_trace['mid_y'].iloc[::-1].rolling(window=3).mean().shift(1).iloc[::-1]
    df_trace['shot_score'] = (df_trace['mid_y'] - df_trace['prev_3']) + (df_trace['mid_y'] - df_trace['next_3'])

    cap = cv2.VideoCapture(args.input_video_path)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(args.output_video_path, fourcc, fps, (frame_width, frame_height))

    BOUNCE_VISUAL_DURATION = 15
    pbar = tqdm(total=total_frames, desc="渲染写入")
    i = 0

    while True:
        ret, frame = cap.read()
        if not ret: break
        if i >= len(court_points_all): break

        canvas = frame

        # A. 场地线绘制
        c_lines = court_lines_pixel_y.get(i)
        if c_lines:
            cv2.line(canvas, (0, c_lines['net_y']), (frame_width, c_lines['net_y']), (255, 255, 0), 2)
            cv2.line(canvas, (0, c_lines['top_baseline_y']), (frame_width, c_lines['top_baseline_y']), (255, 105, 180),
                     1)
            cv2.line(canvas, (0, c_lines['bottom_baseline_y']), (frame_width, c_lines['bottom_baseline_y']),
                     (255, 105, 180), 1)
        draw_court_dots(canvas, court_points_all[i])

        # B. 绿色落点留痕
        for b in final_valid_bounces:
            coord, b_frame = b.get('sub_coord'), b.get('frame')
            if coord is not None and 0 <= (i - b_frame) < BOUNCE_VISUAL_DURATION:
                bx, by = int(coord[0]), int(coord[1])
                cv2.circle(canvas, (bx, by), 12, (0, 255, 0), 2)
                cv2.circle(canvas, (bx, by), 3, (0, 255, 0), -1)
                cv2.putText(canvas, f"GROUND @{b_frame}", (bx + 15, by), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # C. 球员框与人球距离
        b_box = adapted_for_detector[i].get(1)
        ball_valid = b_box is not None
        cx, cy = (int((b_box[0] + b_box[2]) / 2), int((b_box[1] + b_box[3]) / 2)) if ball_valid else (-1, -1)

        p_frame = player_detections.get(i, {})
        for p_id, b in p_frame.items():
            if b is not None:
                cv2.rectangle(canvas, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 255, 0), 2)
                cv2.putText(canvas, f"P{p_id}", (int(b[0]), int(b[1]) - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0),
                            2)
                if ball_valid:
                    dx = max(b[0] - cx, 0, cx - b[2])
                    dy = max(b[1] - cy, 0, cy - b[3])
                    dist = np.sqrt(dx ** 2 + dy ** 2)
                    cv2.putText(canvas, f"Dist: {dist:.1f}", (int(b[0]), int(b[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (0, 255, 255), 2)

        # D. 左上角状态栏
        is_hit, is_cand = i in shot_frames_set, i in candidate_frames_set
        if is_hit:
            status, color, border = "[STATUS] WINNER: FINAL HIT!", (0, 0, 255), 10
            cv2.rectangle(canvas, (0, 0), (frame_width, frame_height), (0, 0, 255), border)
        elif is_cand:
            status, color = "[REJECTED] Group Competition Loser", (180, 180, 180)
        else:
            status, color = f"[REJECTED] Score: {df_trace['shot_score'].iloc[i]:.2f}", (150, 150, 150)

        cv2.putText(canvas, status, (30, 80), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(canvas, status, (30, 80), cv2.FONT_HERSHEY_DUPLEX, 1.0, color, 2)

        # E. 击球公告与轨迹靶标
        canvas = draw_shot_announcements(canvas, i, shot_classifications)
        if ball_valid:
            cv2.drawMarker(canvas, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, 10, 2)

        # ==========================================
        # 💥 绘制层 F: 球员体能数据面板 (左下角跑动距离)
        # ==========================================
        if player_distances is not None:
            # 安全获取当前帧的累计距离，防止越界
            dist_p1 = player_distances.get(1, [0.0] * total_frames)[i] if i < len(player_distances.get(1, [])) else 0.0
            dist_p2 = player_distances.get(2, [0.0] * total_frames)[i] if i < len(player_distances.get(2, [])) else 0.0

            # 格式化显示：超过 1000 米就显示 km
            str_p1 = f"{dist_p1 / 1000:.2f} km" if dist_p1 > 1000 else f"{dist_p1:.1f} m"
            str_p2 = f"{dist_p2 / 1000:.2f} km" if dist_p2 > 1000 else f"{dist_p2:.1f} m"

            # 1. 绘制半透明黑色底板
            overlay = canvas.copy()
            cv2.rectangle(overlay, (30, frame_height - 130), (380, frame_height - 30), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, canvas, 0.4, 0, canvas)

            # 2. 写入 P1 (底部球员) 蓝色数据
            cv2.putText(canvas, "P1 (Bot) Run:", (50, frame_height - 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 200, 200), 1)
            cv2.putText(canvas, str_p1, (210, frame_height - 90), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 100, 100), 2)

            # 3. 写入 P2 (顶部球员) 绿色数据
            cv2.putText(canvas, "P2 (Top) Run:", (50, frame_height - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (200, 255, 200), 1)
            cv2.putText(canvas, str_p2, (210, frame_height - 50), cv2.FONT_HERSHEY_DUPLEX, 0.8, (100, 255, 100), 2)

        out.write(canvas)
        i += 1
        pbar.update(1)

    cap.release()
    out.release()
    pbar.close()

    minimap_output = os.path.join(output_dir, "debug_minimap.mp4")
    print("\n>>> 开始进行单应矩阵精度可视化与沙盘合成...")
    render_with_minimap(
        video_path=args.input_video_path,
        output_path=minimap_output,
        final_coords=final_coords,
        bounces=final_valid_bounces,
        court_ref=court_ref_instance,
        court_matrices_all=court_matrices_all,
        player_detections=player_detections,
        shot_speeds=shot_speed
    )

    # 只需要传入输出目录
    output_json_dir = output_dir
    export_analysis_to_separated_json(
        fps=fps,
        frame_width=frame_width,
        frame_height=frame_height,
        total_frames=frame_idx,
        court_matrices=court_matrices_all,
        adapted_for_detector=adapted_for_detector,
        player_detections=player_detections,
        final_valid_bounces=final_valid_bounces,
        shot_frames_set=shot_frames_set,
        shot_classifications=shot_classifications,
        shot_speeds=shot_speed,
        rally_analysis=rally_analysis,
        net_hit_events=net_hit_events,
        output_dir=output_json_dir
    )
    print(f"\n✅ 渲染全链条完成！多模态工业级成品见: {args.output_video_path}")


if __name__ == "__main__":
    main()
