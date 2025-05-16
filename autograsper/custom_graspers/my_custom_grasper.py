import time, numpy as np, math, os, threading
from grasper import AutograsperBase, RobotActivity
from library.utils import OrderType
from library.rgb_object_tracker import get_object_pos


class MyCustomGrasper(AutograsperBase):
    def __init__(self, config, shutdown_event: threading.Event):
        super().__init__(config, shutdown_event=shutdown_event)
        self.config = config
        # Custom initializations, access config via self.config
        self.target_color = self.config.get("my_grasper_params", {}).get(
            "target_color", "green"
        )
        print(f"MyCustomGrasper initialized for {self.target_color} objects.")

    def startup(self):
        print("MyCustomGrasper: Startup.")
        # Example: Move to home defined in config
        home_xy = self.config.get("experiment", {}).get("robot_home_xy", [0.5, 0.5])
        initial_z = self.config.get("experiment", {}).get("initial_z_height", 1.0)
        orders = [
            (OrderType.MOVE_Z, [initial_z]),
            (OrderType.MOVE_XY, home_xy),
            (OrderType.GRIPPER_OPEN, []),
        ]
        self.queue_orders(orders, record=False)

    def perform_task(self):
        print(f"MyCustomGrasper: Performing task for {self.target_color}.")
        if self.shutdown_event.is_set():
            return

        try:
            # Use self.bottom_image, self.robot_state
            obj_pos = get_object_pos(
                self.bottom_image, self.robot_idx, self.target_color
            )
            if obj_pos is None:
                print(f"{self.target_color} object not found.")
                self.failed = True
                return

            # ... sequence of orders using self.queue_orders(...) ...

            if not self._check_success():  # Implement your success check
                self.failed = True
        except Exception as e:
            print(f"Error in perform_task: {e}")
            self.failed = True
