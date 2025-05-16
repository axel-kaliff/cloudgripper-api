from grasper import AutograsperBase, RobotActivity
from library.utils import run_calibration


class CalibrateGrasper(AutograsperBase):
    def __init__(self, config, shutdown_event):
        super().__init__(config, shutdown_event=shutdown_event)

    def perform_task(self):
        """
        This script is used to calibrate the position of the robot.
        00--01
        |    |
        10--11
        use the above as guide to calibrate the position of the robot, DONT use the move_xy number
        """
        run_calibration(0.2, self.robot)

        self.state = RobotActivity.FINISHED  # stop data recording

    def reset_task(self):
        # replace with your own resetting if needed
        return super().reset_task()
