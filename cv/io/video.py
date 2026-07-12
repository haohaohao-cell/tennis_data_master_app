import cv2
import os

def read_video(video_path):
    cap = cv2.VideoCapture(video_path)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    return frames


def save_video(output_video_frames, output_video_path, fps=24):
    if not output_video_frames:
        print("⚠️ 错误：没有帧可以保存！")
        return False

    output_dir = os.path.dirname(output_video_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    height, width = output_video_frames[0].shape[:2]

    # 优先使用兼容性最好的 mp4v
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    # 如果 mp4v 打不开，尝试 MJPG (保底方案)
    if not out.isOpened():
        print(f"⚠️ mp4v 编码器失败，正在尝试 MJPG 保底...")
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print(f"❌ 严重错误：无法创建视频写入器，请检查路径或权限：{output_video_path}")
        return False

    # 核心：只循环一次写入
    for frame in output_video_frames:
        # 确保帧的尺寸一致，如果不一致 cv2 也会报错
        if (frame.shape[0], frame.shape[1]) != (height, width):
            frame = cv2.resize(frame, (width, height))
        out.write(frame)

    out.release()

    # 最后验证文件
    if os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 0:
        print(f"✅ 视频成功保存 (FPS: {fps}): {output_video_path}")
        return True
    else:
        print(f"⚠️ 警告：视频文件创建失败或为空")
        return False