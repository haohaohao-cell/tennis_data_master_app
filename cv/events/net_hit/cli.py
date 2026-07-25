import argparse

from cv.config import DEFAULT_BALL_MODEL_PATH, OUTPUT_DIR


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run top-down net-hit detection directly on a video.")
    parser.add_argument("--input-video", required=True)
    parser.add_argument("--model-path", default=str(DEFAULT_BALL_MODEL_PATH))
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

    parser.add_argument("--near-net-px", type=float, default=35.0)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    from .video import run_video_net_hit_detection, save_result_json

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
