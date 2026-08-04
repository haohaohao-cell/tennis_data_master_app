import torch
import cv2
import numpy as np
from itertools import groupby
from scipy.spatial import distance
from tqdm import tqdm
from .model import BallTrackerNet
from .general import postprocess
from cv.device import resolve_torch_device


class TrackNetRunner:
    def __init__(self, model_path, device=None):
        """
        初始化 TrackNet 模型，只需加载一次
        """
        self.device = resolve_torch_device(device)
        self.model = BallTrackerNet()
        self.model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
        self.model = self.model.to(self.device)
        self.model.eval()

    # ----------------------
    # 视频读取
    # ----------------------
    @staticmethod
    def read_video(path_video):
        cap = cv2.VideoCapture(path_video)
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        frames = []
        while cap.isOpened():
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            else:
                break
        cap.release()
        return frames, fps

    # ----------------------
    # 三帧推理，返回中间帧球坐标
    # ----------------------
    def infer_model_3_frames(self, f2, f1, f0):
        """
        输入连续三帧 f2, f1, f0 (f2最早，f0最新)
        返回 (x, y) 或 None
        """
        if f2 is None or f1 is None or f0 is None:
            return None
        orig_h, orig_w = f0.shape[:2]
        height, width = 360, 640
        img2 = cv2.resize(f2, (width, height))
        img1 = cv2.resize(f1, (width, height))
        img0 = cv2.resize(f0, (width, height))

        imgs = np.concatenate((img0, img1, img2), axis=2)  # HWC拼接
        imgs = imgs.astype(np.float32) / 255.0
        imgs = np.rollaxis(imgs, 2, 0)  # HWC -> CHW
        inp = np.expand_dims(imgs, axis=0)  # 1,C,H,W

        with torch.no_grad():
            out = self.model(torch.from_numpy(inp).float().to(self.device))

        output = out.argmax(dim=1).detach().cpu().numpy()
        x, y = postprocess(output)

        if x is None or y is None:
            return None
    
        return (x, y)
    def infer_model_3_frames2(self, f2, f1, f0):
        """
        输入连续三帧 f2, f1, f0 (f2最早，f0最新)
        返回 (x, y) 或 None
        """
        if f2 is None or f1 is None or f0 is None:
            return None
        orig_h, orig_w = f0.shape[:2]
        height, width = 360, 640
        img2 = cv2.resize(f2, (width, height))
        img1 = cv2.resize(f1, (width, height))
        img0 = cv2.resize(f0, (width, height))

        imgs = np.concatenate((img0, img1, img2), axis=2)  # HWC拼接
        imgs = imgs.astype(np.float32) / 255.0
        imgs = np.rollaxis(imgs, 2, 0)  # HWC -> CHW
        inp = np.expand_dims(imgs, axis=0)  # 1,C,H,W

        with torch.no_grad():
            out = self.model(torch.from_numpy(inp).float().to(self.device))

        output = out.argmax(dim=1).detach().cpu().numpy()
        x, y = postprocess(output)

        if x is None or y is None:
            return None
        scale_x = orig_w / 1920
        scale_y = orig_h / 1080

        final_x = int(x * scale_x)
        final_y = int(y * scale_y)
        print(f"\n[DEBUG] 视频原尺寸: {orig_w}x{orig_h}")
        print(f"[DEBUG] 模型缩放比: x_scale={scale_x:.2f}, y_scale={scale_y:.2f}")
        print(f"[DEBUG] 模型输出(小图): ({x}, {y})")
        print(f"[DEBUG] 映射后(大图): ({final_x}, {final_y})")
            
            # 这是一个关键自检：如果大图坐标超过了原视频尺寸，说明比例乘反了
        if final_x > orig_w or final_y > orig_h:
            print("⚠️ 警告：映射坐标超出了视频边界！检查 w/h 是否颠倒。")
        return (final_x, final_y)
    # ----------------------
    # 全帧推理（原 infer_model）
    # ----------------------
    def infer_model(self, frames):
        height = 360
        width = 640
        dists = [-1]*2
        ball_track = [(None,None)]*2

        for num in tqdm(range(2, len(frames))):
            img = cv2.resize(frames[num], (width, height))
            img_prev = cv2.resize(frames[num-1], (width, height))
            img_preprev = cv2.resize(frames[num-2], (width, height))

            imgs = np.concatenate((img, img_prev, img_preprev), axis=2)
            imgs = imgs.astype(np.float32)/255.0
            imgs = np.rollaxis(imgs, 2, 0)
            inp = np.expand_dims(imgs, axis=0)

            with torch.no_grad():
                out = self.model(torch.from_numpy(inp).float().to(self.device))

            output = out.argmax(dim=1).detach().cpu().numpy()
            x_pred, y_pred = postprocess(output)
            ball_track.append((x_pred, y_pred))

            if ball_track[-1][0] and ball_track[-2][0]:
                dist = distance.euclidean(ball_track[-1], ball_track[-2])
            else:
                dist = -1
            dists.append(dist)

        return ball_track, dists

    # ----------------------
    # 去除异常点
    # ----------------------
    @staticmethod
    def remove_outliers(ball_track, dists, max_dist=100):
        outliers = list(np.where(np.array(dists) > max_dist)[0])
        for i in outliers:
            if (dists[i+1] > max_dist) | (dists[i+1] == -1):
                ball_track[i] = (None, None)
                outliers.remove(i)
            elif dists[i-1] == -1:
                ball_track[i-1] = (None, None)
        return ball_track

    # ----------------------
    # 分段轨迹
    # ----------------------
    @staticmethod
    def split_track(ball_track, max_gap=4, max_dist_gap=80, min_track=5):
        list_det = [0 if x[0] else 1 for x in ball_track]
        groups = [(k, sum(1 for _ in g)) for k, g in groupby(list_det)]

        cursor = 0
        min_value = 0
        result = []
        for i, (k, l) in enumerate(groups):
            if (k == 1) & (i > 0) & (i < len(groups) - 1):
                dist = distance.euclidean(ball_track[cursor-1], ball_track[cursor+l])
                if (l >= max_gap) | (dist/l > max_dist_gap):
                    if cursor - min_value > min_track:
                        result.append([min_value, cursor])
                        min_value = cursor + l - 1
            cursor += l
        if len(list_det) - min_value > min_track:
            result.append([min_value, len(list_det)])
        return result

    # ----------------------
    # 插值
    # ----------------------
    @staticmethod
    def interpolation(coords):
        def nan_helper(y):
            return np.isnan(y), lambda z: z.nonzero()[0]

        x = np.array([x[0] if x[0] is not None else np.nan for x in coords])
        y = np.array([x[1] if x[1] is not None else np.nan for x in coords])

        nons, yy = nan_helper(x)
        x[nons] = np.interp(yy(nons), yy(~nons), x[~nons])
        nans, xx = nan_helper(y)
        y[nans] = np.interp(xx(nans), xx(~nans), y[~nans])

        track = [*zip(x, y)]
        return track

    # ----------------------
    # 写视频
    # ----------------------
    @staticmethod
    def write_track(frames, ball_track, path_output_video, fps, trace=7):
        height, width = frames[0].shape[:2]
        out = cv2.VideoWriter(path_output_video, cv2.VideoWriter_fourcc(*'DIVX'),
                              fps, (width, height))
        for num in range(len(frames)):
            frame = frames[num]
            for i in range(trace):
                if (num-i > 0):
                    if ball_track[num-i][0]:
                        x = int(ball_track[num-i][0])
                        y = int(ball_track[num-i][1])
                        frame = cv2.circle(frame, (x, y), radius=0, color=(0, 0, 255), thickness=10-i)
                    else:
                        break
            out.write(frame)
        out.release()
