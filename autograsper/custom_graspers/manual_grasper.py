from grasper import AutograsperBase, RobotActivity


class ManualGrasper(AutograsperBase):
    def __init__(self, config, shutdown_event):
        super().__init__(config, shutdown_event=shutdown_event)

    def perform_task(self):
        self.manual_control()

        self.state = RobotActivity.FINISHED  # stop data recording

    def reset_task(self):
        # replace with your own resetting if needed
        return super().reset_task()
