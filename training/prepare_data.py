import os
import shutil
import random
from PIL import Image
import cv2
import numpy as np
import argparse

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'darts')

def resize_images(path_to_images, size=(800, 800)):
    for image_name in os.listdir(path_to_images):
        image = Image.open(os.path.join(path_to_images, image_name))
        image = image.resize(size)
        image.save(os.path.join(path_to_images, image_name))


def change_bb_size(ds_name, bb_size=0.025):
    label_dir = os.path.join(DATA_DIR, "labels")
    path_to_labels = os.path.join(label_dir, ds_name)
    for ds_subset in os.listdir(path_to_labels): 
        for label_name in os.listdir(os.path.join(path_to_labels, ds_subset)):
            path_to_label = os.path.join(path_to_labels, ds_subset, label_name)
            
            new_file = ""
            with open(path_to_label, "r") as f:
                for line in f.readlines():
                    cls, x, y = line.split()[:3]
                    new_file = new_file + f"{cls} {x} {y} {bb_size} {bb_size}\n"
            with open(path_to_label, "w") as f:
                f.write(new_file)


def sharpen_images(ds_name, sharpness_multiplier=5):
    image_dir = os.path.join(DATA_DIR, "images")
    ds_path = os.path.join(image_dir, ds_name)
    new_ds_path = ds_path + "_sharpened"
    
    original_kernel = np.array([[0, 0, 0],
                                [0, 1, 0],
                                [0, 0, 0]])

    blurred_kernel = np.array([[0, 1, 0],
                               [1, 1, 1],
                               [0, 1, 0]])/5
    
    sharp_kernel = original_kernel + (original_kernel - blurred_kernel)*sharpness_multiplier
    
    for ds_subset in os.listdir(ds_path):
        os.makedirs(os.path.join(new_ds_path, ds_subset))
        for image_name in os.listdir(os.path.join(ds_path, ds_subset)):
            path_to_image = os.path.join(ds_path, ds_subset, image_name)
            image = cv2.imread(path_to_image)
            sharp_image = cv2.filter2D(image, -1, sharp_kernel)
            cv2.imwrite(os.path.join(new_ds_path, ds_subset, image_name), sharp_image)
            
        

def split_dataset(dataset_name, val_frac=0.1, test_frac=0.15):
    path_to_data = DATA_DIR
    path_to_labels = os.path.join(path_to_data, 'labels', dataset_name)
    path_to_images = os.path.join(path_to_data, 'images', dataset_name)

    image_names = [f for f in os.listdir(path_to_images) if os.path.isfile(os.path.join(path_to_images, f))]
    random.shuffle(image_names)

    num_val = int(len(image_names)*val_frac)
    num_test = int(len(image_names)*test_frac)

    for ds_type in ['train', 'val', 'test']:
        os.makedirs(os.path.join(path_to_labels, ds_type), exist_ok=True)
        os.makedirs(os.path.join(path_to_images, ds_type), exist_ok=True)

    for image_name in image_names[:num_val]:
        shutil.move(os.path.join(path_to_images, image_name), os.path.join(path_to_images, 'val'))
        shutil.move(os.path.join(path_to_labels, image_name.replace(image_name[-4:], '.txt')), os.path.join(path_to_labels, 'val'))

    for image_name in image_names[num_val:num_val+num_test]:
        shutil.move(os.path.join(path_to_images, image_name), os.path.join(path_to_images, 'test'))
        shutil.move(os.path.join(path_to_labels, image_name.replace(image_name[-4:], '.txt')), os.path.join(path_to_labels, 'test'))
    
    for image_name in image_names[num_val+num_test:]:
        shutil.move(os.path.join(path_to_images, image_name), os.path.join(path_to_images, 'train'))
        shutil.move(os.path.join(path_to_labels, image_name.replace(image_name[-4:], '.txt')), os.path.join(path_to_labels, 'train'))


if __name__ == '__main__':
    # datasets are folders under data/darts/images (and data/darts/labels), e.g. "collected"
    parser = argparse.ArgumentParser(description='Pre-process a dataset in data/darts')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('split', help='move images and labels into train/val/test folders')
    p.add_argument('dataset')
    p.add_argument('--val', type=float, default=0.1)
    p.add_argument('--test', type=float, default=0.15)
    p = sub.add_parser('sharpen', help='write a sharpened copy of the dataset to <dataset>_sharpened')
    p.add_argument('dataset')
    p = sub.add_parser('resize', help='resize every image in a folder in place (default 800x800)')
    p.add_argument('folder')
    p.add_argument('--size', type=int, default=800)
    p = sub.add_parser('boxes', help='set every bounding box in the dataset\'s split label folders to the same size')
    p.add_argument('dataset')
    p.add_argument('--size', type=float, default=0.025)
    args = parser.parse_args()

    if args.command == 'split':
        split_dataset(args.dataset, args.val, args.test)
    elif args.command == 'sharpen':
        sharpen_images(args.dataset)
    elif args.command == 'resize':
        resize_images(args.folder, (args.size, args.size))
    elif args.command == 'boxes':
        change_bb_size(args.dataset, args.size)
