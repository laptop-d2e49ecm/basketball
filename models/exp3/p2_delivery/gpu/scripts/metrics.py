"""Custom single-class 101-point AP; same protocol as previous SSDLite runs."""
import numpy as np
IOU_THRESHOLDS=np.round(np.arange(.5,.951,.05),2)
def progress(message): print(message,flush=True)
def iou_matrix(a, b):
    a = np.asarray(a, dtype=np.float64).reshape(-1, 4)
    b = np.asarray(b, dtype=np.float64).reshape(-1, 4)
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    lo = np.maximum(a[:, None, :2], b[None, :, :2])
    hi = np.minimum(a[:, None, 2:], b[None, :, 2:])
    intersection = np.clip(hi - lo, 0, None).prod(axis=2)
    aa = np.clip(a[:, 2:] - a[:, :2], 0, None).prod(axis=1)
    bb = np.clip(b[:, 2:] - b[:, :2], 0, None).prod(axis=1)
    return intersection / np.maximum(aa[:, None] + bb[None, :] - intersection, 1e-12)


def score_detections(predictions, ground_truth):
    """One-class 101-recall AP, IoU .50:.05:.95, max100/image, no crowd.

    Custom evaluator: this is NOT a claim of complete pycocotools equivalence.
    All sizes are evaluated together, without area bins or ignore regions.
    """
    n_gt = sum(len(b) for b in ground_truth.values())
    ranked = []
    for name, pred in predictions.items():
        order = np.argsort(-np.asarray(pred["scores"]), kind="stable")[:100]
        for j in order:
            ranked.append((name, float(pred["scores"][j]), np.asarray(pred["boxes"][j])))
    ranked.sort(key=lambda x: -x[1])
    ap_list = []
    p25 = r25 = 0.0
    for threshold in IOU_THRESHOLDS:
        used = {name: np.zeros(len(boxes), dtype=bool) for name, boxes in ground_truth.items()}
        tp = np.zeros(len(ranked), dtype=np.float64)
        for j, (name, confidence, box) in enumerate(ranked):
            gt = ground_truth[name]
            if len(gt) == 0:
                continue
            overlaps = iou_matrix(box[None], gt)[0]
            overlaps[used[name]] = -1
            match = int(overlaps.argmax())
            if overlaps[match] >= threshold - 1e-10:
                tp[j] = 1
                used[name][match] = True
        if len(tp):
            tpc = np.cumsum(tp)
            recall = tpc / max(n_gt, 1)
            precision = tpc / np.arange(1, len(tp) + 1)
            envelope = np.maximum.accumulate(precision[::-1])[::-1]
            sampled = []
            for rr in np.linspace(0, 1, 101):
                indices = np.flatnonzero(recall >= rr - 1e-12)
                sampled.append(float(envelope[indices[0]]) if len(indices) else 0.0)
            ap = float(np.mean(sampled)) if n_gt else 0.0
        else:
            ap = 0.0
        ap_list.append(ap)
        if threshold == 0.5:
            selected = np.array([p[1] >= 0.25 for p in ranked], dtype=bool)
            hits = float(tp[selected].sum())
            p25 = hits / max(int(selected.sum()), 1)
            r25 = hits / max(n_gt, 1)
    return {
        "AP50": ap_list[0], "AP50_95": float(np.mean(ap_list)),
        "AP_by_IoU": {str(t): a for t, a in zip(IOU_THRESHOLDS, ap_list)},
        "precision_conf025_iou050": p25, "recall_conf025_iou050": r25,
        "gt_boxes": n_gt, "images": len(ground_truth), "predictions": len(ranked),
    }


def self_test():
    gt = {"a": np.array([[0, 0, 10, 10]], dtype=float)}
    perfect = {"a": {"boxes": np.array([[0, 0, 10, 10]]), "scores": np.array([0.9])}}
    assert abs(score_detections(perfect, gt)["AP50_95"] - 1) < 1e-12
    assert score_detections({}, gt)["AP50_95"] == 0
    duplicate = {"a": {"boxes": np.array([[20, 20, 30, 30], [0, 0, 10, 10]]),
                       "scores": np.array([0.99, 0.8])}}
    assert abs(score_detections(duplicate, gt)["AP50_95"] - 0.5) < 1e-12
    gt2 = {"a": np.array([[0, 0, 10, 10], [20, 20, 30, 30]])}
    half = score_detections(perfect, gt2)
    assert abs(half["AP50"] - 51 / 101) < 1e-12
    assert half["precision_conf025_iou050"] == 1
    assert half["recall_conf025_iou050"] == 0.5
    wrong = {"a": {"boxes": np.array([[100, 100, 110, 110]]), "scores": np.array([0.9])}}
    assert score_detections(wrong, gt)["AP50_95"] == 0
    progress("SELF_TEST_OK: perfect, empty, false-positive-first, partial recall, unmatched")


