import cv2
import numpy as np


def _track_box(track):
    left, top, right, bottom = track.to_ltrb()
    return [float(left), float(top), float(right), float(bottom)]


def _box_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _appearance_hist(frame, box):
    x1, y1, x2, y2 = map(int, box[:4])
    x1 = max(0, min(frame.shape[1] - 1, x1))
    x2 = max(0, min(frame.shape[1], x2))
    y1 = max(0, min(frame.shape[0] - 1, y1))
    y2 = max(0, min(frame.shape[0], y2))
    if x2 <= x1 or y2 <= y1:
        return None

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    h = crop.shape[0]
    torso = crop[int(h * 0.15):int(h * 0.65), :]
    if torso.size == 0:
        torso = crop

    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0.0, 1.0, cv2.NORM_MINMAX)
    return hist


class PlayerIdentityManager:
    """Keep P1/P2 stable when top_player and bottom_player swap court sides."""

    def __init__(self, min_match_score=0.35):
        self.min_match_score = min_match_score
        self.track_to_identity = {}
        self.identities = {
            "P1": {"hist": None, "last_box": None, "last_frame": -1, "last_side": None},
            "P2": {"hist": None, "last_box": None, "last_frame": -1, "last_side": None},
        }

    def update(self, tracks, frame, frame_idx):
        player_tracks = [
            track
            for track in tracks
            if track.is_confirmed()
            and getattr(track, "det_class", None) in ("bottom_player", "top_player")
        ]
        used_identities = set()

        for track in player_tracks:
            track.stable_identity = None

            identity = self.track_to_identity.get(track.track_id)
            if identity is None:
                continue

            self._update_identity(identity, track, frame, frame_idx)
            track.stable_identity = identity
            used_identities.add(identity)

        unassigned = [
            track for track in player_tracks if getattr(track, "stable_identity", None) is None
        ]

        for track in unassigned:
            identity = self._match_identity(track, frame, frame_idx, used_identities)
            if identity is None:
                identity = self._initial_identity_for_side(
                    getattr(track, "det_class", None),
                    used_identities,
                )
            if identity is None:
                continue

            self.track_to_identity[track.track_id] = identity
            self._update_identity(identity, track, frame, frame_idx)
            track.stable_identity = identity
            used_identities.add(identity)

        return tracks

    def _initial_identity_for_side(self, side, used_identities):
        preferred = {"bottom_player": "P1", "top_player": "P2"}.get(side)
        if (
            preferred
            and preferred not in used_identities
            and self.identities[preferred]["last_box"] is None
        ):
            return preferred

        for identity, state in self.identities.items():
            if identity not in used_identities and state["last_box"] is None:
                return identity
        return None

    def _match_identity(self, track, frame, frame_idx, used_identities):
        box = _track_box(track)
        hist = _appearance_hist(frame, box)
        center = _box_center(box)

        best_identity = None
        best_score = -1.0
        for identity, state in self.identities.items():
            if identity in used_identities or state["last_box"] is None:
                continue

            score = 0.0
            if hist is not None and state["hist"] is not None:
                similarity = cv2.compareHist(hist, state["hist"], cv2.HISTCMP_CORREL)
                score += 0.75 * max(0.0, similarity)

            last_center = _box_center(state["last_box"])
            distance = np.hypot(center[0] - last_center[0], center[1] - last_center[1])
            score += 0.25 * max(0.0, 1.0 - distance / max(frame.shape[0], frame.shape[1]))

            if frame_idx - state["last_frame"] <= 30:
                score += 0.10

            if score > best_score:
                best_score = score
                best_identity = identity

        return best_identity if best_score >= self.min_match_score else None

    def _update_identity(self, identity, track, frame, frame_idx):
        box = _track_box(track)
        hist = _appearance_hist(frame, box)
        state = self.identities[identity]

        if hist is not None:
            if state["hist"] is None:
                state["hist"] = hist
            else:
                state["hist"] = cv2.addWeighted(state["hist"], 0.85, hist, 0.15, 0.0)

        state["last_box"] = box
        state["last_frame"] = frame_idx
        state["last_side"] = getattr(track, "det_class", None)
