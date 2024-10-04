import argparse
import logging
import os
import asyncio
import json
import traceback
from configparser import ConfigParser
from typing import Optional, Tuple, Any, List

import numpy as np
from autograsper import Autograsper, RobotActivity
from recording import Recorder

from library.rgb_object_tracker import all_objects_are_visible

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ERROR_EVENT = asyncio.Event()

class TaskManager:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    async def cancel_all_tasks(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


class RecorderManager:
    def __init__(self, output_dir: str, robot_idx: str, config: dict):
        self.output_dir = output_dir
        self.recorder = self.setup_recorder(output_dir, robot_idx, config)

    def setup_recorder(self, output_dir: str, robot_idx: str, config: dict) -> Recorder:
        session_id = "test"
        camera_matrix = np.array(config["camera"]["m"])
        distortion_coefficients = np.array(config["camera"]["d"])
        token = os.getenv("ROBOT_TOKEN")
        if not token:
            raise ValueError("ROBOT_TOKEN environment variable not set")
        return Recorder(session_id, output_dir, camera_matrix, distortion_coefficients, token, robot_idx)

    async def start_recording(self, task_dir: str):
        await asyncio.to_thread(self.recorder.start_new_recording, task_dir)

    async def stop_recording(self):
        await asyncio.to_thread(self.recorder.write_final_image)
        self.recorder.stop()


class SharedState:
    def __init__(self):
        self.state: RobotActivity = RobotActivity.STARTUP
        self.recorder_manager: Optional[RecorderManager] = None


shared_state = SharedState()

def load_config(config_file: str = "stack_from_scratch/config.ini") -> dict:
    config = ConfigParser()
    config.read(config_file)
    config_dict = {}
    for section in config.sections():
        config_dict[section] = {key: json.loads(value) if value.startswith("[") or value.startswith("{") else value for key, value in config.items(section)}
    return config_dict


def get_new_session_id(base_dir: str) -> int:
    if not os.path.exists(base_dir):
        return 1
    session_ids = [
        int(dir_name) for dir_name in os.listdir(base_dir) if dir_name.isdigit()
    ]
    return max(session_ids, default=0) + 1


def handle_error(exception: Exception) -> None:
    logger.error(f"Error occurred: {exception}")
    logger.error(traceback.format_exc())
    ERROR_EVENT.set()


def create_new_data_point(script_dir: str) -> Tuple[str, str, str]:
    recorded_data_dir = os.path.join(script_dir, "recorded_data")
    new_session_id = get_new_session_id(recorded_data_dir)
    new_session_dir = os.path.join(recorded_data_dir, str(new_session_id))
    task_dir = os.path.join(new_session_dir, "task")
    restore_dir = os.path.join(new_session_dir, "restore")

    os.makedirs(task_dir, exist_ok=True)
    os.makedirs(restore_dir, exist_ok=True)

    return new_session_dir, task_dir, restore_dir


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robot Controller")
    parser.add_argument("--robot_idx", type=str, required=True, help="Robot index")
    parser.add_argument(
        "--config",
        type=str,
        default="config.ini",
        help="Path to the configuration file",
    )
    return parser.parse_args()


def initialize(args: argparse.Namespace) -> Tuple[Autograsper, dict, str]:
    config = load_config(args.config)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    autograsper = Autograsper(args, config)
    return autograsper, config, script_dir


async def run_autograsper(autograsper: Autograsper, colors: List[str], block_heights: np.ndarray, config: dict) -> None:
    try:
        await asyncio.to_thread(autograsper.run_grasping, colors, block_heights, config)
    except Exception as e:
        handle_error(e)


async def monitor_state(autograsper: Autograsper) -> None:
    try:
        while not ERROR_EVENT.is_set():
            if shared_state.state != autograsper.state:
                shared_state.state = autograsper.state
                if shared_state.state == RobotActivity.FINISHED:
                    break
            await asyncio.sleep(0.1)
    except Exception as e:
        handle_error(e)


async def monitor_bottom_image(recorder: Recorder, autograsper: Autograsper) -> None:
    try:
        while not ERROR_EVENT.is_set():
            if recorder and recorder.bottom_image is not None:
                autograsper.bottom_image = np.copy(recorder.bottom_image)
            await asyncio.sleep(0.1)
    except Exception as e:
        handle_error(e)


async def start_new_recording(session_dir: str, task_dir: str, restore_dir: str, autograsper: Autograsper, args: argparse.Namespace, config: dict, task_manager: TaskManager) -> None:
    autograsper.output_dir = task_dir
    if not shared_state.recorder_manager:
        shared_state.recorder_manager = RecorderManager(task_dir, args.robot_idx, config)
        task_manager.create_task(run_recorder(shared_state.recorder_manager.recorder))
        task_manager.create_task(monitor_bottom_image(shared_state.recorder_manager.recorder, autograsper))
    await shared_state.recorder_manager.start_recording(task_dir)
    await asyncio.sleep(0.5)
    autograsper.start_flag = True


async def reset_experiment(session_dir: str, restore_dir: str, autograsper: Autograsper, colors: List[str]) -> None:
    status_message = (
        "success"
        if not all_objects_are_visible(colors, shared_state.recorder_manager.recorder.bottom_image, debug=False)
        else "fail"
    )
    if status_message == "fail":
        autograsper.failed = True

    logger.info(status_message)
    with open(os.path.join(session_dir, "status.txt"), "w") as status_file:
        status_file.write(status_message)

    autograsper.output_dir = restore_dir
    await shared_state.recorder_manager.start_recording(restore_dir)


async def handle_state_changes(
    autograsper: Autograsper,
    config: dict,
    script_dir: str,
    colors: List[str],
    args: argparse.Namespace,
    task_manager: TaskManager,
) -> None:
    prev_robot_activity = RobotActivity.STARTUP
    session_dir, task_dir, restore_dir = "", "", ""

    while not ERROR_EVENT.is_set():
        if shared_state.state != prev_robot_activity:
            if prev_robot_activity != RobotActivity.STARTUP and shared_state.recorder_manager:
                await shared_state.recorder_manager.stop_recording()

            if shared_state.state == RobotActivity.ACTIVE:
                session_dir, task_dir, restore_dir = create_new_data_point(script_dir)
                await start_new_recording(session_dir, task_dir, restore_dir, autograsper, args, config, task_manager)

            elif shared_state.state == RobotActivity.RESETTING:
                await reset_experiment(session_dir, restore_dir, autograsper, colors)

            prev_robot_activity = shared_state.state

        if shared_state.state == RobotActivity.FINISHED:
            if shared_state.recorder_manager:
                await shared_state.recorder_manager.stop_recording()
                await asyncio.sleep(1)
            break

        await asyncio.sleep(0.1)


async def main():
    args = parse_arguments()
    autograsper, config, script_dir = initialize(args)
    task_manager = TaskManager()

    colors = config["experiment"]["colors"]
    block_heights = np.array(config["experiment"]["block_heights"])

    autograsper_task = task_manager.create_task(run_autograsper(autograsper, colors, block_heights, config))
    monitor_state_task = task_manager.create_task(monitor_state(autograsper))

    try:
        await handle_state_changes(autograsper, config, script_dir, colors, args, task_manager)
    except Exception as e:
        handle_error(e)
    finally:
        ERROR_EVENT.set()
        await task_manager.cancel_all_tasks()


if __name__ == "__main__":
    asyncio.run(main())