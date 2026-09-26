"""Fine-tune the Dart Sense YOLO model on a dataset.

Starts from the model the game currently uses (play/weights.pt) and trains further with the tuned
hyperparameters from the original training run (train_optimal.sh). Examples:

    python train.py --data data/sample.yaml --epochs 3            # smoke test on the bundled sample
    python train.py --data data/collected.yaml --epochs 50 --install
"""
import argparse
import os
import shutil
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY_WEIGHTS = os.path.join(HERE, '..', 'play', 'weights.pt')

# found with YOLO's genetic tuner (134 iterations of 25 epochs), see README.md
TUNED = dict(lr0=0.00517, lrf=0.00761, momentum=0.90098, weight_decay=0.00038, warmup_epochs=1.94204,
             warmup_momentum=0.42999, box=2.99452, cls=0.30763, dfl=1.53753, hsv_h=0.00695, hsv_s=0.45949,
             hsv_v=0.24372, degrees=15.58584, translate=0.10067, scale=0.2181, shear=0.0, perspective=0.0,
             flipud=0.0, fliplr=0.31783, mosaic=0.61939, mixup=0.0, copy_paste=0.0)


def resolve_dataset(data_yaml, run_dir):
    # ultralytics resolves a relative 'path' against its global datasets dir, so pin it to the yaml's folder
    with open(data_yaml) as f:
        cfg = yaml.safe_load(f)
    root = cfg.get('path', '.')
    if not os.path.isabs(root):
        root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(data_yaml)), root))
    cfg['path'] = root

    missing = []
    for split in ('train', 'val', 'test'):
        dirs = cfg.get(split) or []
        for d in dirs if isinstance(dirs, list) else [dirs]:
            if not os.path.exists(os.path.join(root, d)):
                missing.append(os.path.join(root, d))
    if missing:
        sys.exit('Dataset folders not found:\n  ' + '\n  '.join(missing))

    os.makedirs(run_dir, exist_ok=True)
    resolved = os.path.join(run_dir, 'dataset.yaml')
    with open(resolved, 'w') as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return resolved


def install(best):
    target = os.path.normpath(PLAY_WEIGHTS)
    if os.path.exists(target):
        shutil.copy2(target, target.replace('.pt', '.previous.pt'))
    shutil.copy2(best, target)
    print(f'Installed {best} as {target} (the old model is kept as weights.previous.pt)')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', required=True, help='dataset yaml (YOLO format)')
    parser.add_argument('--weights', default=PLAY_WEIGHTS, help='model to start from (default: play/weights.pt, or e.g. yolov8n.pt to train from scratch)')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--imgsz', type=int, default=800, help='the model was trained and runs at 800')
    parser.add_argument('--batch', type=int, default=-1, help='-1 picks the largest batch that fits in GPU memory')
    parser.add_argument('--device', default=None, help='e.g. 0, cpu (default: GPU if available)')
    parser.add_argument('--name', default='finetune', help='run name under training/runs/')
    parser.add_argument('--no-tuned', action='store_true', help="use ultralytics' default hyperparameters")
    parser.add_argument('--install', action='store_true', help='copy the best weights to play/weights.pt when done')
    args = parser.parse_args()

    from ultralytics import YOLO # slow import, after argument errors

    project = os.path.join(HERE, 'runs')
    data = resolve_dataset(args.data, os.path.join(project, 'datasets', args.name))
    model = YOLO(args.weights)
    hyper = {} if args.no_tuned else TUNED
    model.train(data=data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=args.device,
                workers=0, project=project, name=args.name, exist_ok=False, **hyper)

    best = os.path.join(str(model.trainer.save_dir), 'weights', 'best.pt')
    print(f'Best weights: {best}')
    if args.install:
        install(best)
    else:
        print('Run again with --install, or copy it to play/weights.pt, to use it in the game')


if __name__ == '__main__':
    main()
