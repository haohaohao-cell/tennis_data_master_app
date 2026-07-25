from .model import BallTrackerNet
import torch
from .datasets import trackNetDataset
from .general import validate
from cv.device import get_torch_device
import argparse

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--batch_size', type=int, default=2, help='batch size')
    parser.add_argument('--model_path', type=str, help='path to model')
    args = parser.parse_args()

    device = get_torch_device()
    pin_memory = device.type == 'cuda'

    val_dataset = trackNetDataset('val')
    val_loader = torch.utils.data.DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=1,
        pin_memory=pin_memory
    )

    model = BallTrackerNet()
    model.load_state_dict(torch.load(args.model_path, map_location="cpu", weights_only=True))
    model = model.to(device)

    val_loss, precision, recall, f1 = validate(model, val_loader, device, -1)

