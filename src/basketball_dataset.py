# -*- coding: utf-8 -*-
"""任务 1.3.2：PyTorch Dataset 封装（视觉检测数据集）。

用法示例：
    from src.basketball_dataset import BasketballDataset
    from torch.utils.data import DataLoader

    train_set = BasketballDataset("data/splits/yolo/images/train", imgsz=640)
    loader = DataLoader(train_set, batch_size=8, shuffle=True,
                        collate_fn=BasketballDataset.collate_fn)
    batch = next(iter(loader))
    print(batch["image"].shape, len(batch["boxes"][0]))

返回 dict：{"image": float32 张量 (C,H,W)，"boxes": (N,4) xywh 归一化框，"classes": (N,)}
（0=player；collate_fn 处理每张图框数不同的变长目标。）
"""
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset


class BasketballDataset(Dataset):
    """YOLO 目录结构数据集：images/<split>/xxx.jpg 对应 labels/<split>/xxx.txt。"""

    def __init__(self, image_dir, imgsz=640, transform=None):
        self.image_dir = Path(image_dir)
        self.imgsz = imgsz
        self.transform = transform
        # YOLO 目录结构: yolo/{images,labels}/<split>/，images 的上上级才是 labels
        self.label_dir = self.image_dir.parent.parent / "labels" / self.image_dir.name
        self.samples = [
            p for p in sorted(self.image_dir.glob("*.jpg"))
            if (self.label_dir / f"{p.stem}.txt").exists()
        ]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path = self.samples[idx]
        with Image.open(img_path) as im:
            im = im.convert("RGB").resize((self.imgsz, self.imgsz))
            img_t = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1).float() / 255.0

        label_path = self.label_dir / f"{img_path.stem}.txt"
        boxes, classes = [], []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 5:
                c, cx, cy, w, h = (float(v) for v in parts)
                classes.append(c)
                boxes.append([cx, cy, w, h])

        if self.transform:
            img_t = self.transform(img_t)

        return {
            "image": img_t,
            "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            "classes": torch.tensor(classes, dtype=torch.long),
        }

    @staticmethod
    def collate_fn(batch):
        """变长目标批合并：boxes/classes 按列表堆叠，便于送入检测模型。"""
        return {
            "image": torch.stack([b["image"] for b in batch]),
            "boxes": [b["boxes"] for b in batch],
            "classes": [b["classes"] for b in batch],
        }


if __name__ == "__main__":
    ds = BasketballDataset("data/splits/yolo/images/train")
    print(f"数据集规模: {len(ds)}")
    if len(ds):
        sample = ds[0]
        print(f"图像张量: {tuple(sample['image'].shape)}，框数: {len(sample['boxes'])}")
