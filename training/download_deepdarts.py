"""Download the DeepDarts D1/D2 images (McNally et al. 2021) and convert their labels to YOLO format.

Images: https://huggingface.co/datasets/bhabha-kapil/Dartboard-Detection-Dataset (16,050 images, already
cropped to the board and resized to 800x800, ~3.4 GB in 17 tar shards, streamed and extracted without
keeping the tars). Labels: the DeepDarts labels.pkl, as the JSON copy in the Dart-Vision repository.

Writes data/darts/{images,labels}/deepdarts_{d1,d2}/{train,val,test}/ using the official DeepDarts split,
which data/deepdarts.yaml trains on. Re-running skips shards that finished, so an interrupted download resumes.
"""
import argparse
import hashlib
import json
import os
import shutil
import tarfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DARTS_DIR = os.path.join(HERE, 'data', 'darts')

HF_SHARD = 'https://huggingface.co/datasets/bhabha-kapil/Dartboard-Detection-Dataset/resolve/main/shards/dartboard-images-{:03d}.tar'
NUM_SHARDS = 17
# pinned so the labels can't change underneath us; this file matches the DeepDarts labels.pkl
LABELS_URL = 'https://raw.githubusercontent.com/iambhabha/Dart-Vision/ec4f4daf264083a8fd4dda404d2bf17a7cfd4fb6/dataset/labels.json'
LABELS_SHA256 = 'a1639f586a1ffba7f1260403d191aa17512b654b394b6a9b95af1593ef982c7b'

# official DeepDarts split (dataloader.py in github.com/wmcnally/deep-darts): whole sessions are held out
VAL = {'d1_02_06_2020', 'd1_02_16_2020', 'd1_02_22_2020', 'd2_02_03_2021', 'd2_02_05_2021'}
TEST = {'d1_03_03_2020', 'd1_03_19_2020', 'd1_03_23_2020', 'd1_03_27_2020', 'd1_03_28_2020', 'd1_03_30_2020',
        'd1_03_31_2020', 'd2_03_03_2020', 'd2_02_10_2021', 'd2_02_03_2021_2'}

BOX = 0.025 # bounding box size used for all points, as in the original training
EDGE = 0.02 # darts up to this far outside the crop are clipped onto the edge, further out they are dropped


def split_of(folder):
    return 'val' if folder in VAL else 'test' if folder in TEST else 'train'


def target(folder, name):
    # e.g. deepdarts_d1/train/d1_02_04_2020_IMG_1093.JPG
    return os.path.join(f'deepdarts_{folder[:2]}', split_of(folder), f'{folder}_{name}')


def get(url, retries=5):
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(url, timeout=60)
        except OSError as e:
            if attempt == retries - 1:
                raise
            print(f'  {e}, retrying')
            time.sleep(2 ** attempt)


def load_labels():
    path = os.path.join(DARTS_DIR, 'deepdarts_labels.json')
    if not os.path.exists(path):
        print('Downloading labels...')
        with get(LABELS_URL) as r, open(path + '.part', 'wb') as f:
            shutil.copyfileobj(r, f)
        os.replace(path + '.part', path)
    with open(path, 'rb') as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != LABELS_SHA256:
        raise SystemExit(f'{path} does not match the expected labels, delete it and run again')
    return {(v['img_folder'], v['img_name']): v['xy'] for v in json.loads(data).values()}


def yolo_label(xy):
    lines, dropped = [], 0
    for i, (x, y) in enumerate(xy):
        cls = i if i < 4 else 4 # the first 4 points are the 20, 3, 11, 6 calibration points, the rest darts
        if not (-EDGE <= x <= 1 + EDGE and -EDGE <= y <= 1 + EDGE):
            dropped += 1
            continue
        x, y = min(max(x, 0), 1), min(max(y, 0), 1)
        lines.append(f'{cls} {x:.6f} {y:.6f} {BOX} {BOX}')
    return '\n'.join(lines) + '\n', dropped


def write_labels(labels):
    dropped = 0
    for (folder, name), xy in labels.items():
        path = os.path.join(DARTS_DIR, 'labels', os.path.splitext(target(folder, name))[0] + '.txt')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        text, n = yolo_label(xy)
        dropped += n
        with open(path, 'w') as f:
            f.write(text)
    print(f'Wrote {len(labels)} label files ({dropped} darts outside the image dropped)')


def download_shard(index, labels):
    done_marker = os.path.join(DARTS_DIR, '.deepdarts', f'shard-{index:03d}.done')
    if os.path.exists(done_marker):
        return 0
    count = 0
    with get(HF_SHARD.format(index)) as r:
        # stream the tar straight from the response, so the shards never touch the disk
        with tarfile.open(fileobj=r, mode='r|') as tar:
            for member in tar:
                if not member.isfile():
                    continue
                folder, name = member.name.replace('\\', '/').split('/')[-2:]
                if (folder, name) not in labels:
                    continue
                path = os.path.join(DARTS_DIR, 'images', target(folder, name))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with tar.extractfile(member) as src, open(path + '.part', 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.replace(path + '.part', path)
                count += 1
    os.makedirs(os.path.dirname(done_marker), exist_ok=True)
    open(done_marker, 'w').close()
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--labels-only', action='store_true', help="only (re)write the YOLO labels")
    args = parser.parse_args()

    os.makedirs(DARTS_DIR, exist_ok=True)
    labels = load_labels()
    write_labels(labels)
    if args.labels_only:
        return
    for index in range(1, NUM_SHARDS + 1):
        print(f'Shard {index}/{NUM_SHARDS}...', flush=True)
        try:
            n = download_shard(index, labels)
        except (OSError, tarfile.TarError) as e:
            raise SystemExit(f'Shard {index} failed ({e}), run again to resume')
        print(f'  {n} images' if n else '  already downloaded')

    images = os.path.join(DARTS_DIR, 'images')
    missing = [k for k in labels if not os.path.exists(os.path.join(images, target(*k)))]
    print(f'{len(labels) - len(missing)}/{len(labels)} images present')
    if missing:
        print('Missing, e.g.:', ', '.join('/'.join(k) for k in missing[:5]))


if __name__ == '__main__':
    main()
