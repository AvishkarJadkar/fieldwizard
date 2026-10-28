# Model weights

FieldWizard needs a YOLOv8 detector fine-tuned on football footage. Weights are
**not** committed to the repository (they are large and licensed separately).

Expected location:

```
models/football_v8.pt
```

The model must expose these four classes (indices are read at runtime, order
does not matter):

| index | class |
| --- | --- |
| 0 | `ball` |
| 1 | `goalkeeper` |
| 2 | `player` |
| 3 | `referee` |

If the file is missing, `run.py` falls back to a stock COCO model
(`yolo11n.pt`), which **cannot** separate players from the ball well enough for
the analytics — you will see poor tracking and no ball.

## Options

1. **Any fine-tuned YOLOv8 football model** with the four classes above. The
   Roboflow community "Football Players Detection" dataset trains exactly this
   class set and is the usual starting point.
2. Fine-tune your own: start from `yolov8n.pt`, train on the Roboflow dataset
   (~300 ball/goalkeeper/player/referee images from broadcast footage), then
   drop the produced weights here.

Point to an alternative file with `FW_MODEL` (see `.env.example`) without
renaming anything.
