# Project Autograsper: Custom Grasper Development Guide

## 1. Introduction

The Autograsper project is a robot action execution and data recording framework for the CloudGripper robot.

## 2. Prerequisites

Install required pip packages in a venv:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Core Concepts

### 3.1. `AutograsperBase`
A custom grasper inherits from `grasper.AutograsperBase`.

* **`__init__(self, config, shutdown_event)`**: Call `super().__init__`. Initializes `GripperRobot`, state flags, threading events, and reads common parameters from `config`.
* **State Machine (`run_grasping`)**: Cycles through `RobotActivity` states (STARTUP, ACTIVE, RESETTING). This loop is managed by the `DataCollectionCoordinator`.
* **Key Overridable Methods**:
    * `startup(self)`: Pre-task setup.
    * `perform_task(self)`: Main task logic.
    * `reset_task(self)`: Post-success reset.
    * `recover_after_fail(self)`: Post-failure recovery.
* **Robot Interaction**:
    * `queue_orders(self, order_list, ...)`: Executes a list of `(OrderType, params)` commands.
    * `record_current_state(self)`: Signals coordinator to save current state (image, telemetry).
* **Data from Coordinator**:
    * `self.bottom_image`: Latest camera image.
    * `self.robot_state`: Latest robot telemetry.
    * `self.output_dir`: Directory for recorded data.
* **Shutdown**: Monitor `self.shutdown_event.is_set()` in long operations. Use `sleep_with_shutdown()`.

## 4. Steps to Create a Custom Autograsper

### Step 1: Create Grasper File
1.  New Python file (e.g., `autograsper/custom_graspers/my_grasper.py`).
2.  Imports:
```python
import time, numpy as np, math, os, threading
from grasper import AutograsperBase, RobotActivity
from library.utils import OrderType, sleep_with_shutdown
from library.rgb_object_tracker import get_object_pos
```

### Step 2: Define Custom Grasper Class
```python
class MyCustomGrasper(AutograsperBase):
    def __init__(self, config, shutdown_event: threading.Event):
        super().__init__(config, shutdown_event=shutdown_event)
        # Custom initializations, access config via self.config
        self.target_color = self.config.get("my_grasper_params", {}).get("target_color", "green")
        print(f"MyCustomGrasper initialized for {self.target_color} objects.")
```

### Step 3: Implement Core Logic Methods
Override `startup`, `perform_task`, `reset_task`, `recover_after_fail` as needed.

##### **`startup(self)`**:
Initial robot setup (e.g., move to home).
  ```python
  def startup(self):
      print("MyCustomGrasper: Startup.")
      # Example: Move to home defined in config
      home_xy = self.config.get("experiment", {}).get("robot_home_xy", [0.5, 0.5])
      initial_z = self.config.get("experiment", {}).get("initial_z_height", 1.0)
      orders = [
          (OrderType.MOVE_Z, [initial_z]),
          (OrderType.MOVE_XY, home_xy),
          (OrderType.GRIPPER_OPEN, [])
      ]
      self.queue_orders(orders, record=False)
  ```


##### **`perform_task(self)`**: 
Main task. Set `self.failed = True` on error.
  ```python
  def perform_task(self):
      print(f"MyCustomGrasper: Performing task for {self.target_color}.")
      if self.shutdown_event.is_set(): return

      try:
          # Use self.bottom_image, self.robot_state
          obj_pos = get_object_pos(self.bottom_image, self.robot_idx, self.target_color)
          if obj_pos is None:
              print(f"{self.target_color} object not found.")
              self.failed = True
              return

          # ... sequence of orders using self.queue_orders(...) ...

          if not self._check_success(): # Implement your success check
              self.failed = True
      except Exception as e:
          print(f"Error in perform_task: {e}")
          self.failed = True
  ```
##### **`reset_task(self)`**: 
Reset after success. Clear `self.failed = False`.
##### **`recover_after_fail(self)`**:
Attempt recovery. Often calls `reset_task()`.

### Step 5: Configuration (Example `config.yaml`)
Your grasper accesses parameters via `self.config`. This dictionary is loaded from a YAML file.
```yaml
# Example config.yaml structure
camera:
  m: # Camera matrix
    - [505.245, 0.0, 324.509]
    - [0.0, 505.645, 233.541]
    - [0.0, 0.0, 1.0]
  d: [-0.077, -0.047, 0.121, -0.096] # Distortion coefficients
  record: true
  fps: 2.5
  record_only_after_action: false
  save_images_individually: true
  # clip_length: 300 # Optional

experiment:
  name: "my_custom_task"
  robot_idx: "robot1"
  timeout_between_experiments: 2.0
  time_between_orders: 1.5 # Default time between orders for this grasper
  # Grasper-specific settings can be nested
  grasper_type: "MyCustomGrasper" # Used by main script to load correct grasper
  robot_home_xy: [0.5, 0.5] # Example custom param
  initial_z_height: 1.0 # Example custom param

my_grasper_params: # Custom section for your grasper
  target_color: "blue"
  grasp_approach_height: 0.05
```
Access in code: `self.config.get('experiment', {}).get('time_between_orders', 2.0)`

### Step 7: Integration with `main.py`
The `main.py` script handles loading and running a specific grasper based on the configuration.
1.  Place your custom grasper file (e.g., `my_custom_grasper.py`) in a discoverable location, like the `custom_graspers/` directory.
2.  Import your grasper in `main.py`:
    ```python
    # In main.py
    # from custom_graspers.backgammon_grasper import BackgammonGrasper
    # from custom_graspers.manual_grasper import ManualGrasper
    from custom_graspers.my_custom_grasper import MyCustomGrasper # Add your grasper
    ```
3.  Modify the grasper instantiation logic in `main.py`'s `main()` function to select your grasper. You can use the `grasper_type` from your `config.yaml`:
    ```python
    # In main.py's main() function:
    config = load_config(config_path)
    shutdown_event = threading.Event()
    active_grasper: AutograsperBase # For type hinting

    grasper_type_from_config = config.get("experiment", {}).get("grasper_type", "RandomGrasper") # Default if not specified

    if grasper_type_from_config == "MyCustomGrasper":
        active_grasper = MyCustomGrasper(config, shutdown_event=shutdown_event)
    elif grasper_type_from_config == "ManualGrasper":
        active_grasper = ManualGrasper(config, shutdown_event=shutdown_event)
    # Add other elif blocks for other graspers
    # elif grasper_type_from_config == "BackgammonGrasper":
    #     active_grasper = BackgammonGrasper(config, shutdown_event=shutdown_event, task="pick-and-place") # Example with extra args
    else: # Fallback or default
        print(f"Warning: Grasper type '{grasper_type_from_config}' not explicitly handled or unknown. Falling back to RandomGrasper.")
        from custom_graspers.random_grasping_task import RandomGrasper # Ensure this import exists
        active_grasper = RandomGrasper(config, shutdown_event=shutdown_event)

    global_coordinator = DataCollectionCoordinator(config, active_grasper, shutdown_event)
    # ... rest of main()
    ```
4.  Ensure your `config.yaml` (e.g., `autograsper/backgammon-config.yaml` as referenced in `main.py`) has `grasper_type: "MyCustomGrasper"` under the `experiment` section.

## Running the System & Testing

1.  **Configure**:
    * Ensure your `.env` file has `CLOUDGRIPPER_TOKEN`.
    * Modify your chosen `config.yaml` (e.g., `autograsper/backgammon-config.yaml`) to:
        * Set `experiment.grasper_type` to your custom grasper's class name (e.g., `"MyCustomGrasper"`).
        * Adjust other parameters like `robot_idx`, recording settings, and any custom parameters your grasper needs.
2.  **Run `main.py`**:
    Execute the main script from the project's root directory:
    ```bash
    python main.py
    ```
    This will:
    * Load the configuration.
    * Instantiate your selected autograsper.
    * Start the `DataCollectionCoordinator`.
    * Start a Flask web server (default: `http://0.0.0.0:3000`).
3.  **Monitor & Test**:
    * Open `http://localhost:3000/video_feed` in a web browser to see the live camera feed (if configured and working).
    * Observe the console output for logs from your grasper and the coordinator.
    * Check the `recorded_data/` directory (or as configured) for saved images, videos, and state JSON files.
    * Thoroughly test task execution, error handling, and recovery.
4.  **Shutdown**:
    * Press `Ctrl+C` in the terminal where `main.py` is running to shut down the application. The `shutdown_event` will be set, allowing threads to terminate gracefully.

