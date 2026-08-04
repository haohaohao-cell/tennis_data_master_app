import argparse
from pathlib import Path

from cv.config import DEFAULT_COURT_MODEL_PATH, DEFAULT_GRIDTRACKNET_MODEL_PATH, OUTPUT_DIR


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run net-hit detection directly on a video.")
    parser.add_argument("--input-video", required=True)
    parser.add_argument("--model-path", default=str(DEFAULT_GRIDTRACKNET_MODEL_PATH))
    parser.add_argument("--output-json", default=str(OUTPUT_DIR / "net_hit_result.json"))
    parser.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto")
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--end-frame", type=int, default=None)

    net = parser.add_mutually_exclusive_group(required=True)
    net.add_argument("--net-y", type=float, help="Horizontal net y-coordinate in image pixels.")
    net.add_argument(
        "--net-line",
        nargs=4,
        type=float,
        metavar=("X1", "Y1", "X2", "Y2"),
        help="Two points on the net line in image pixels.",
    )
    net.add_argument("--auto-net", action="store_true", help="Locate the curved net automatically from the video.")
    parser.add_argument("--ball-track-json", type=Path, help="Existing frame-aligned ball-track JSON.")
    parser.add_argument("--court-model", default=str(DEFAULT_COURT_MODEL_PATH))

    parser.add_argument("--near-net-px", type=float, default=35.0)
    parser.add_argument("--near-band-px", type=float, default=10.0, help="Curved-net band margin in pixels.")
    parser.add_argument("--min-confidence", type=float, default=0.55)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.ball_track_json and not args.auto_net:
        raise SystemExit("--ball-track-json requires --auto-net")
    from .video import extract_ball_track, run_video_net_hit_detection, save_result_json

    if args.auto_net:
        from .curved_detector import CurvedNetHitConfig
        from .curved_video import run_curved_net_hit_detection
        from .track_io import load_track_from_json

        if args.ball_track_json:
            coords, _, _ = load_track_from_json(str(args.ball_track_json))
        else:
            track = extract_ball_track(
                args.input_video,
                args.model_path,
                args.device,
                start_frame=0,
                end_frame=None,
            )
            coords = track["coords"]
        result = run_curved_net_hit_detection(
            args.input_video,
            coords,
            court_model_path=args.court_model,
            device=args.device,
            start_frame=args.start_frame,
            end_frame=args.end_frame,
            detector_config=CurvedNetHitConfig(
                min_confidence=args.min_confidence,
                band_margin_px=args.near_band_px,
            ),
        )
    else:
        result = run_video_net_hit_detection(
            input_video=args.input_video,
            model_path=args.model_path,
            device=args.device,
            start_frame=args.start_frame,
            end_frame=args.end_frame,
            net_y=args.net_y,
            net_line=tuple(args.net_line) if args.net_line else None,
            near_net_px=args.near_net_px,
            min_confidence=args.min_confidence,
        )
    save_result_json(result, args.output_json)

    print(f"Saved net-hit result to {args.output_json}")
    print(f"Detected likely net hits: {result['net_hit_count']}")
    for event in result["events"]:
        print(
            f"frame={event['frame']} time={event['time_sec']:.3f}s "
            f"confidence={event['confidence']:.3f} reason={event['reason']}"
        )


if __name__ == "__main__":
    main()
