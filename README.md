# Dart Sense
## [Live Demo: A leg of 301](https://www.youtube.com/watch?v=8a97sVmbqY0)
[![Live Demo: Automated Dart Scoring](https://img.youtube.com/vi/8a97sVmbqY0/0.jpg)]([https://www.youtube.com/watch?v=8a97sVmbqY0])

This project is licensed for non-commercial, non-distributable use only. Please contact me if you'd like to use it beyond personal experimentation.
## Description
Dart Sense is an automatic dart scoring application. It uses a sophisticated deep learning-based computer vision model to track the landing coordinates of darts and 4 board calibration points in an image in order to predict the scores for each dart. This app can be used to score a game of darts in real time using video streamed from a smartphone.

A YOLOv8 object detection model was trained to detect dart positions and board calibration points. By comparing the coordinates of the calibration points in an image to the standardised dart board dimensions, you can then transform the image, allowing any set of coordinates to be mapped to a darts score. I developed this system for my Artifical Intelligence Msc Dissertation project. Since completing my studies, I have continued to work on this project, collecting more data to further improve the model and developing a fully functional GUI to run the system in real time, with added game logic to be able to play a game of darts with real players without the burden of scoring it yourself. Please see a video demonstration of the app below!

## Setup
1. Clone the repository: `git clone https://github.com/bnww/dart-sense.git`
2. Install [uv](https://docs.astral.sh/uv/) and the system packages for score calling (eSpeak NG) and the Tkinter fallback GUI (Tk), e.g. on Arch: `sudo pacman -S uv espeak-ng tk`.
   Running `./start.sh` creates the virtual environment (`.venv`, Python 3.14) and installs `play/requirements.txt` on first run. To do it by hand:
   ```
   uv venv --python 3.14 .venv
   uv pip install -r play/requirements.txt
   source .venv/bin/activate
   ```
3. Download 'IP Webcam' on your smartphone so that you can stream video from your smartphone camera to the app for processing.

## Features
- Automatic scoring works on any dart board and with any darts!
- Stream from your smartphone camera
- Score tracking for various dart games (x01, cricket)
- Play solo or with up to 6 friends
- Customizable settings

![image output 1](images/0022_151123_2715.png)

Example images fed into the YOLO Object Detection model. 'YOLO model prediction' shows the YOLO predicted classes and respective probabilities. 'Predicted scores after transformation' shows the result after processing the YOLO results. The calibration points (corner of 20, 6, 3, and 11 segments) are used to transform the dart coordinates to a standardised reference frame, so that they can be attributed with scores. This allows accurate scoring regardless of the angle or distance of the camera to the board, so it can be used in any playing set-up!

![image output 2](images/d2_02_03_2021_2_DSC_0059.JPG)


## Usage
1. Run `./start.sh` to launch the app. It opens in its own browser window (Chromium/Chrome if installed); use `./start.sh --no-window` to just serve it at http://127.0.0.1:8765/. The original Tkinter interface is still available with `python play/GUI.py`.
2. Add up to 8 players and configure the match (first to / best of, legs or sets, 301/501/701/custom, straight/double/master in and out). **Important: set the camera address to the IP shown when you start your IP Webcam server.**<br />
![app set up screen](images/set_up_screen.png)
3. Play. Turn on **Save training data** on the setup screen to collect images for improving the model while you play (see Training). Darts are scored automatically: after three darts (or a finish/bust) the score is called, and it's recorded once the darts are pulled out. You can also type a visit total and press Enter, press Enter with an empty box to commit fewer than three detected darts (bounce-outs), undo the last visit (Ctrl+Z), and drag the dart markers on the camera view to correct them.

## Project layout
```
start.sh              sets up .venv and launches the game
play/                 everything needed to play
  app.py              web app (Flask) - the main entry point
  web/                the browser UI (match setup and game screens)
  engine.py           runs the model on the camera stream and turns detections into visits
  training_data.py    saves labelled frames of played visits for training
  match.py            x01 rules: legs/sets, first to/best of, in/out modes
  get_scores.py       maps dart coordinates to scores via the calibration points
  video_processing.py camera reading and GPU/CPU selection, plus the Tkinter scoring loop
  GUI.py, game_logic.py  the original Tkinter app
  weights.pt          the trained YOLOv8 model
  requirements.txt
training/             everything needed to train the model further (own venv and requirements.txt)
  train.py            fine-tune a model on a dataset
  download_deepdarts.py  download the DeepDarts D1/D2 images and convert their labels
  prepare_data.py     split/sharpen/resize a dataset, normalise bounding boxes
  accuracy.py         accuracy metrics (visit PCS, precision, recall, ...)
  data/               dataset configs and a 10-image sample (data/darts/images|labels/small_sample)
  train_optimal.sh    the original training command (Docker, from-scratch run)
  experiments/        the alternative Hough-line/colour scoring approach (not used by the app)
```

## Training
The model can be trained further. The training code is a thin wrapper around [Ultralytics YOLO](https://docs.ultralytics.com/modes/train/). Three sources of data are available:
- **DeepDarts D1 + D2** (McNally et al. 2021): 16,050 labelled images, about two thirds of the data the model was originally trained on. `download_deepdarts.py` fetches them (~3.4 GB) from the [Dartboard Detection Dataset](https://huggingface.co/datasets/bhabha-kapil/Dartboard-Detection-Dataset) on Hugging Face, where they are already cropped to 800x800. It converts the DeepDarts labels to YOLO format and splits them the same way as the DeepDarts paper, holding out whole sessions for val/test.
- **Your own board**: frames saved while you play (below). This is the best way to improve accuracy for your own board, darts, lighting and camera angle.
- The dissertation's own ~8,000 images (D3-D7, see `data/d1_to_d7.yaml`) are not published, apart from the 10-image sample in `data/darts/images/small_sample`.

1. Create the training environment. It is separate from the game's, since training needs extra libraries and no web/speech ones:
   ```
   uv venv --python 3.14 training/.venv
   uv pip install --python training/.venv/bin/python -r training/requirements.txt
   source training/.venv/bin/activate
   cd training
   ```
2. Check that training works: `python train.py --data data/sample.yaml --epochs 1 --batch 4`
3. Download DeepDarts: `python download_deepdarts.py`. Re-running it resumes an interrupted download.
4. Collect images from your board (optional, but recommended). Turn on **Save training data** on the match setup screen and play as normal. When a visit is recorded, the app saves the last frame with all of that visit's darts in the board to `training/data/darts/images/collected/`, with a YOLO label in `training/data/darts/labels/collected/`. The label holds the calibration points and the final dart positions, including any corrections you made. The game screen shows how many frames have been saved.
   - Visits where you dragged, added or deleted a marker are always saved (`web_..._corrected.jpg`). They show the model its own mistakes, so they are the most valuable.
   - Visits nobody touched mostly repeat what the model already knows, so only every 5th is saved (`web_..._auto.jpg`).
   - Visits entered by typing a total are not saved, because they don't say where the darts landed.

   Untouched visits are labelled with the model's own detections, so a mistake nobody noticed would be learned as correct. Look through the images before training, and fix labels with [LabelImg](https://github.com/HumanSignal/labelImg) if needed (`data/darts/classes.txt` has the class names). The **Save data** button in the Tkinter app (`python play/GUI.py`) saves to the same folders. Then split them into train/val/test with `python prepare_data.py split collected`, and add `images/collected/train` and `images/collected/val` to the lists in `data/deepdarts.yaml`. Mixing them with DeepDarts keeps the model from forgetting other boards.
5. Fine-tune from the current model and install the result into the game:
   ```
   python train.py --data data/deepdarts.yaml --epochs 50 --install
   ```
   This trains at 800x800 with the tuned hyperparameters. Runs are saved in `training/runs/`, and `--install` copies the best weights to `play/weights.pt`, keeping the old model as `play/weights.previous.pt`. To compare models on the held-out sessions, run `yolo val model=<weights> data=runs/datasets/<run name>/dataset.yaml split=test imgsz=800`. `--weights yolov8n.pt` trains from scratch instead. See `python train.py --help` for the other options.

Classes: `0: 20, 1: 3, 2: 11, 3: 6` are the calibration points (the top left corner of the double segment of those numbers), `4: dart` is a dart tip, and `5: 9, 6: 15` are extra calibration points. Boxes are 0.025 x 0.025 (`python prepare_data.py boxes <dataset>` sets them).

## Methodology
### Data Collection and Pre-Processing
For this project, open source data from McNally et al. 2021 was used, consisting of ~16,000 images. This data was collected by the authors who played darts and took photos of the board after each throw. I collected a further 8,000 images in order to provide a greater variety of data for the object detection model to train on. These images were collected from Youtube videos, as well as my own playing set-up, allowing for an array of different playing configurations (e.g dart type, board type, colours, lighting, camera angles) to be sampled.

After collecting the images, further pre-processing was completed to ensure that the images were in the right form for the object detection model. All images were resized to 800x800 pixels in alignment with D1 and D2 from McNally et al. 2021. Furthermore, some of the lower resolution data from videos were sharpened to visually improve the visibility of edges within the images.

Finally, each data set was split into training (75%), validation (10%), and testing (15%) subsets using random sampling.

### Data labelling
All of the collected images required manual labelling for the object detection model. The program ’LabelImg’ was used for this. It has a GUI which shows the images and allows the user to draw bounding boxes for chosen classes, and then save the labels in the YOLO format. Each data set was loaded into the program and each image was labelled by hand. The labels were pre-processed to change the sizes of all the bounding boxes to 0.025 (2.5% of the image’s size) as this has been shown to work well for D1 and D2 (McNally et al. 2021).

Once a sufficiently accurate model had been trained, I was able to use this to make predictions for the rest of the unlabelled data, and then validate and change the annotations as necessary upon review.

### Training
You Only Look Once (YOLO) object detection was used to detect the landing positions of the
darts as well as 4 dart board calibration points. YOLOv8n was
used as this has the best benchmark results, and the nano size was used as it is important that the model is able to run in real time.

Model tuning is crucial in order to get the best results. Manual experiments and using YOLO’s tuning algorithm were used to find the best hyperparameters for training. The YOLOv8 genetic tuning algorithm was used to find the best hyperparameters for the model over many iterations. The model was tuned for 134 iterations each consisting of 25 epochs. For each iteration, the fitness of the hyperparameters is evaluated based on the performance of the model.

Comparing the F1 scores for a model using trained hyperparameters compared to the default values shows the benefits of tuning (shown below). D5 is an especially difficult dataset, taken from a unique video. No data from D5 was used to train the model, so the much improved performance on this data set is indicative of a model that can generalise effectively. This is likely due to the data augmentation being used in the tuned model. It used image rotation, scaling, translation and brightness/contrast adjustments.

<img src="images/hyperparameters.png" alt="alt text" width="50%">

### Score Prediction
In order to use the predicted dart locations from the YOLO model, the coordinates need to be contextualised with reference to some measure of the standardised dart board dimensions. The standardised dimensions of the dart board were used to generate coordinates for 4 calibration points around the board. The chosen points are the upper left corner of the double segments for the 20, 6, 3 and 11, illustrated in 3.2b. The YOLO model is trained to
detect these same calibration points on the images, so then the image can be transformed to the reference plane, and dart positions can be scored using the standardised board segment dimensions. This allows for darts to be accurately scored regardless of camera angle and any distortion effects in the image.

![alt text](images/transformation.png)

I tried another approach to the score prediction, which used a combination of Hough line detection and pixel colour analysis in order to segment the board. Lines were detected to delineate segments, then colour masks were used to find green and red segments. Following a line to the bullseye, the scoring multiplier was computed based on the number of green, red and other areas the line passes through. This method had many failure cases due to the colour of the darts themselves obscurring the board. This method is not used in the final app.

![alt text](images/1054_171023_48.png)

### Results
Results were evaluated based on the following custom metrics:
![alt text](images/accuracy_metrics.png)

The final model was trained for 100 epochs with the YOLOv8n (nano) architecture using
tuned hyperparameters and a batch size of 79.

Here are the final results on test data:
| Image PCS | Precision | Recall | Missed | Extra |
|-----------|-----------|--------|--------|-------|
| 0.884     | 0.977     | 0.942  | 0.040  | 0.004 |

The main failure cases are due to dart obfuscation. To an extent it becomes an impossible task, as even humans can't be 100% sure of a dart's score, and rely on moving in order to get a better viewpoint. I do believe that with more data to train the model this can imperove further and it will be able to exceed human performance on the task.

Here is an example where a dart is missed as the tip cannot be seen:
![alt text](images/1258_171023_581.png)
