# Fetch `notebook_utils` module
import urllib.request
urllib.request.urlretrieve(
    url='https://raw.githubusercontent.com/openvinotoolkit/openvino_notebooks/main/notebooks/utils/notebook_utils.py',
    filename='notebook_utils.py'
)


### Imports
import collections
import time

import cv2
import numpy as np
from pathlib import Path
from IPython import display
from ipywidgets import interactive, ToggleButtons
import openvino as ov

import notebook_utils as utils

# Option to select differenct styles
styleButtons = ToggleButtons(
        options = ['MOSAIC'],
        description = "Click one of the styles you want to use for the style transfer",
        disabled = False,
        style = {'description_width':'300px'})

## The Model
 
### Download the Model

# Directory to download the model from ONNX model zoo
base_model_dir = "model"
base_url = "https://github.com/onnx/models/raw/main/vision/style_transfer/fast_neural_style/model"

# Selected ONNX model will be downloaded in the path
model_path = Path(f"{styleButtons.value.lower()}-9.onnx")

style_url = f"{base_url}/{model_path}"
utils.download_file(style_url, directory=base_model_dir)


# Construct the command for model conversion API.

ov_model = ov.convert_model(f"model/{styleButtons.value.lower()}-9.onnx")
ov.save_model(ov_model, f"model/{styleButtons.value.lower()}-9.xml")


# Converted IR model path
ir_path = Path(f"model/{styleButtons.value.lower()}-9.xml")
onnx_path = Path(f"model/{model_path}")


### Load the Model
 
# Initialize OpenVINO Runtime.
core = ov.Core()


# Read the network and corresponding weights from IR Model.
model = core.read_model(model=ir_path)



import ipywidgets as widgets

device = widgets.Dropdown(
    options=core.available_devices + ["AUTO"],
    value='AUTO',
    description='Device:',
    disabled=False,
)


compiled_model = core.compile_model(model=model, device_name=device.value)

# Get the input and output nodes.
input_layer = compiled_model.input(0)
output_layer = compiled_model.output(0)


print(input_layer.any_name, output_layer.any_name)
print(input_layer.shape)
print(output_layer.shape)

# Get the input size.
N, C, H, W = list(input_layer.shape)


### Preprocess the image 
 
# 1. Preprocess a frame to convert from `unit8` to `float32`.
# 2. Transpose the array to match with the network input size


# Preprocess the input image.
def preprocess_images(frame, H, W):
    """
    
    Preprocess input image to align with network size

    Parameters:
        :param frame:  input frame 
        :param H:  height of the frame to style transfer model
        :param W:  width of the frame to style transfer model
        :returns: resized and transposed frame
    
    """
    image = np.array(frame).astype('float32')
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    image = cv2.resize(src=image, dsize=(H, W), interpolation=cv2.INTER_AREA)
    image = np.transpose(image, [2, 0, 1])
    image = np.expand_dims(image, axis=0)
    return image



# Postprocess the result        
def convert_result_to_image(frame, stylized_image) -> np.ndarray:
    """
    
    Postprocess stylized image for visualization

    Parameters:
        :param frame:  input frame 
        :param stylized_image:  stylized image with specific style applied
        :returns: resized stylized image for visualization
    
    """
    h, w = frame.shape[:2]
    stylized_image = stylized_image.squeeze().transpose(1, 2, 0)
    stylized_image = cv2.resize(src=stylized_image, dsize=(w, h), interpolation=cv2.INTER_CUBIC)
    stylized_image = np.clip(stylized_image, 0, 255).astype(np.uint8)
    stylized_image = cv2.cvtColor(stylized_image, cv2.COLOR_BGR2RGB)
    return stylized_image


### Main Processing Function

def run_style_transfer(source=0, flip=False, use_popup=False, skip_first_frames=0):
    """
    
    Main function to run the style inference:
    1. Create a video player to play with target fps (utils.VideoPlayer).
    2. Prepare a set of frames for style transfer.
    3. Run AI inference for style transfer.
    4. Visualize the results.
    Parameters:
        source: The webcam number to feed the video stream with primary webcam set to "0", or the video path.  
        flip: To be used by VideoPlayer function for flipping capture image.
        use_popup: False for showing encoded frames over this notebook, True for creating a popup window.
        skip_first_frames: Number of frames to skip at the beginning of the video. 
    
    """
    # Create a video player to play with target fps.
    player = None
    try:
        player = utils.VideoPlayer(source=source, flip=flip, fps=30, skip_first_frames=skip_first_frames)
        # Start video capturing.
        player.start()
        if use_popup:
            title = "Press ESC to Exit"
            cv2.namedWindow(winname=title, flags=cv2.WINDOW_GUI_NORMAL | cv2.WINDOW_AUTOSIZE)

        processing_times = collections.deque()
        while True:
            # Grab the frame.
            frame = player.next()
            if frame is None:
                print("Source ended")
                break
            # If the frame is larger than full HD, reduce size to improve the performance.
            scale = 720 / max(frame.shape)
            if scale < 1:
                frame = cv2.resize(src=frame, dsize=None, fx=scale, fy=scale,
                                   interpolation=cv2.INTER_AREA)
            # Preprocess the input image.

            image = preprocess_images(frame, H, W)
           
            # Measure processing time for the input image.
            start_time = time.time()
            # Perform the inference step.
            stylized_image = compiled_model([image])[output_layer]
            stop_time = time.time()

            # Postprocessing for stylized image.
            result_image = convert_result_to_image(frame, stylized_image)

            processing_times.append(stop_time - start_time)
            # Use processing times from last 200 frames.
            if len(processing_times) > 200:
                processing_times.popleft()
            processing_time_det = np.mean(processing_times) * 1000

            # Visualize the results.
            f_height, f_width = frame.shape[:2]
            fps = 1000 / processing_time_det
            cv2.putText(result_image, text=f"Inference time: {processing_time_det:.1f}ms ({fps:.1f} FPS)", 
                        org=(20, 40),fontFace=cv2.FONT_HERSHEY_COMPLEX, fontScale=f_width / 1000,
                        color=(0, 0, 255), thickness=1, lineType=cv2.LINE_AA)
            
            # Use this workaround if there is flickering.
            if use_popup:
                cv2.imshow(title, result_image)
                key = cv2.waitKey(1)
                # escape = 27
                if key == 27:
                    break
            else:
                # Encode numpy array to jpg.
                _, encoded_img = cv2.imencode(".jpg", result_image, params=[cv2.IMWRITE_JPEG_QUALITY, 90])
                # Create an IPython image.
                i = display.Image(data=encoded_img)
                # Display the image in this notebook.
                display.clear_output(wait=True)
                display.display(i)
    # ctrl-c
    except KeyboardInterrupt:
        print("Interrupted")
    # any different error
    except RuntimeError as e:
        print(e)
    finally:
        if player is not None:
            # Stop capturing.
            player.stop()
        if use_popup:
            cv2.destroyAllWindows()



run_style_transfer(source=0, flip=True, use_popup=True)

'''
### Run Style Transfer on a Video File

video_file = "https://storage.openvinotoolkit.org/repositories/openvino_notebooks/data/data/video/Coco%20Walking%20in%20Berkeley.mp4"
run_style_transfer(source=video_file, flip=False, use_popup=False)
'''
