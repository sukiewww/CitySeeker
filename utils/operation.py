import os
from collections import deque
from datetime import datetime

import cv2
import json
import base64
import numpy as np
from pyproj import Geod
from pathlib import Path
from numpy import ndarray
from functools import wraps
from typing import Dict, Union
from string import ascii_uppercase

from .items import ChoiceReActNode, ViewPointPosition, Direction, MultiModels


def get_store_json_path(
        gt_json: str,
        db_name: str,
        agent: MultiModels,
        log_level: str
) -> str:
    section = Path(gt_json).parent.name

    store = Path(__file__).parent.parent / "output_dir" / db_name / section / "trajectories"
    store.mkdir(exist_ok=True, parents=True)
    store_json = store / f"{agent.name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{Path(gt_json).name}"

    os.environ["STORE_JSON"] = store_json.as_posix()
    os.environ["CITY_NAME"] = db_name
    os.environ["SECTION"] = section
    os.environ["AGENT"] = agent.name
    os.environ["LOG_LEVEL"] = log_level

    return store_json.as_posix()


def image_to_base64(image: ndarray) -> str:
    _, buffer = cv2.imencode('.jpg', image)

    return f"data:image/jpeg;base64,{base64.b64encode(buffer.data).decode('utf-8')}"


def read_json(json_file: str) -> dict:
    from loguru import logger
    logger.info(f"Initializing start point from file: {Path(json_file).name}.")

    with open(json_file, mode="r", encoding="utf-8") as f:
        data = {
            "data": json.load(f)
        }

    logger.info(f"Initialized with {len(data['data'])} trajectories.")

    return data


def check_env_variables():
    required_vars = [
        "NEO4J_PASSWORD", "OPENAI_API_BASE", "OPENAI_API_KEY",
        "IMAGE_STORE", "PANO_MODE", "LLM_DIR", "MODEL_NAME",
        "NEO4J_VOLUME"
    ]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            missing_vars = [var for var in required_vars if var not in os.environ]
            if missing_vars:
                raise EnvironmentError(
                    f"Missing environment variables: {', '.join(missing_vars)}, please set in .env file")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_choice_parsed(
        data: ChoiceReActNode,
        perspective_nums: int
) -> ChoiceReActNode:
    from utils.map_logger import logger

    if isinstance(data.observation, str):
        if "\\u" in data.observation:
            logger.error(f"Unicode text found: {data.observation}, retrying...")
        observation: Dict[Union[str, int], str] = json.loads(data.observation)

    else:
        for key, value in data.observation.items():
            if "\\u" in key:
                logger.error(f"Unicode text found: {key}, retrying...")
                raise ValueError
            elif "\\u" in value:
                logger.error(f"Unicode text found: {value}, retrying...")
                raise ValueError

        observation: Dict[Union[str, int], str] = data.observation.copy()

    # if not data.action.isnumeric() and not data.action.isalpha():
    #     logger.error(f"Invalid action: {data.action} received, retrying...")
    #     raise ValueError

    # if data.action.isnumeric() or isinstance(data.action, int):
    #     logger.warning(f"Invalid action: {data.action} received, converted to {ascii_uppercase[int(data.action)]}")
    #     if int(data.action) + 1 > perspective_nums:
    #         logger.error(
    #             f"Invalid action: {data.action} received, over total perspectives {perspective_nums}, retrying...")
    #         raise ValueError
    #     data.action = ascii_uppercase[int(data.action)]

    if data.action.isnumeric() or isinstance(data.action, int):
        logger.warning(f"Invalid action: {data.action} received, converted to {ascii_uppercase[int(data.action)]}")
        if int(data.action) + 1 > perspective_nums:
            logger.error(
                f"Invalid action: {data.action} received, over total perspectives {perspective_nums}, retrying...")
            # raise ValueError
            data.action = ascii_uppercase[perspective_nums - 1]
        else:
            data.action = ascii_uppercase[int(data.action)]

    if data.action.isalpha():
        index = ascii_uppercase.index(data.action)
        if index + 1 > perspective_nums:
            logger.error(
                f"Invalid action: {data.action} received, over total perspectives {perspective_nums}, retrying...")
            # raise ValueError
            data.action = ascii_uppercase[perspective_nums - 1]
            
    # if data.action.isalpha():
    #     index = ascii_uppercase.index(data.action)
    #     if index + 1 > perspective_nums:
    #         logger.error(
    #             f"Invalid action: {data.action} received, over total perspectives {perspective_nums}, retrying...")
    #         raise ValueError

    if len(data.action) != 1:
        logger.error(f"Invalid action: {data.action} received, which is not able to be parsed, retrying...")
        raise ValueError

    if len(observation) != perspective_nums:
        logger.error(
            f"The number of observations should be {perspective_nums}, but got {len(observation)}, retrying...")
        raise ValueError

    observation_updated = observation.copy()

    for key, value in observation.items():
        if key.isnumeric() or isinstance(key, int):
            alpha_key = ascii_uppercase[int(key)]
            observation_updated.update(
                {alpha_key: observation_updated.pop(key)}
            )
            logger.warning(f"Invalid Image index encountered! Convert {key} to {alpha_key}")

    data.observation = observation_updated

    return data


class Compass:
    _geodestic = Geod(ellps="WGS84")

    @classmethod
    def get_step_forward_azimuth(cls,
                                 last_position: ViewPointPosition,
                                 curr_position: ViewPointPosition
                                 ) -> float:
        azimuth, back_azimuth, distance = cls._geodestic.inv(
            lons1=last_position.longitude, lats1=last_position.latitude,
            lons2=curr_position.longitude, lats2=curr_position.latitude,
        )

        return azimuth

    @classmethod
    def get_relative_direction(cls,
                               forward_azimuth: float,
                               heading: float) -> Direction:
        forward_azimuth = forward_azimuth % 360
        heading = heading % 360

        relative_angle = (heading - forward_azimuth + 360) % 360
        index = int((relative_angle + 22.5) // 45) % 8

        return Direction.get_direction_by_index(index)




def is_increasing(steps: Union[list, deque]):
    return np.all(np.diff(steps) >= 0)

def find_closest_value(target: float, lst: list):
    lst = np.array(lst)
    index = (np.abs(lst - target)).argmin()
    return index
