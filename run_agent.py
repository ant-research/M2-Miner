import os
import time
import random
import string
import io
import copy
import subprocess
import sys
import json
import base64
import re
import logging
from pydantic import BaseModel, ValidationError
from PIL import Image
from datetime import datetime, timedelta
from qwen_vl_utils import smart_resize
from openai import OpenAI

from agent.controller import *
from agent.mobile_action_model import *
from agent.system_prompt import get_agent_system_prompt_for_qwen_vl_en

# Suppress all warnings
import warnings

warnings.filterwarnings("ignore")

logger = logging.getLogger()
debug = True


# 把原图像resize为new_width, new_height宽高
def resize_image(img, new_width, new_height):
    return img.resize((new_width, new_height), Image.LANCZOS)


def encode_image_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str


# 定义超时处理函数
def timeout_handler(signum, frame):
    raise Exception("输入超时!")


def get_real_dates(data_key):
    # 当前日期
    today = datetime.now().date()
    # 初始化结果字典
    date_dict = {}

    for key in data_key:
        if key == "今天":
            date_dict[key] = today.strftime("%Y年%m月%d日")
        elif key == "明天":
            date_dict[key] = (today + timedelta(days=1)).strftime("%Y年%m月%d日")
        elif key == "后天":
            date_dict[key] = (today + timedelta(days=2)).strftime("%Y年%m月%d日")
        elif key == "大后天":
            date_dict[key] = (today + timedelta(days=3)).strftime("%Y年%m月%d日")
        else:
            print("data_key 中包含了未定义的日期关键词")

    return date_dict


def model_agent_infer(
    sqe_json,
    client,
    model_name,
    tips="",
):

    def is_valid_json(json_str):
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError:
            return False

    def check_and_extract_xml(xml_string):
        # 定义标签的正则模式
        tool_call_pattern = r"<tool_call>(.*?)</tool_call>"
        summary_pattern = r"<action_description>(.*?)</action_description>"

        # 使用 re.DOTALL 让 . 匹配换行符
        flags = re.DOTALL | re.IGNORECASE

        # 提取内容
        tool_call_match = re.search(tool_call_pattern, xml_string, flags)
        summary_match = re.search(summary_pattern, xml_string, flags)

        if not all([tool_call_match, summary_match]):
            missing = []
            if not tool_call_match:
                missing.append("tool_call")
            if not summary_match:
                missing.append("action_description")
            return False, f"缺少必需的标签: {', '.join(missing)}", None

        # 提取并去除首尾空白
        tool_call_text = tool_call_match.group(1).strip()
        summary_text = summary_match.group(1).strip()

        return (
            True,
            "结构正确且包含所有必需的标签",
            {
                "tool_call": tool_call_text,
                "action_description": summary_text,
            },
        )

    def is_valid_tool_call(tool_call_dict: dict, validata_model: BaseModel):
        try:
            x = validata_model(**tool_call_dict)
            return True
        except ValidationError:
            return False

    summary_history = []
    base64_image = None
    img_resize = None
    img_size = (0, 0)
    try:
        for i in range(len(sqe_json)):
            step_json = sqe_json[i]
            episode_id = step_json["episode_id"]
            step_id = step_json["step_id"]
            instruction = step_json["instruction"]
            image_path = step_json["image_path"]
            summary = step_json["Operation"]

            if i < len(sqe_json) - 1:
                summary_history.append(summary)

    except Exception as e:
        print(f"input json error: {e}")
        return sqe_json

    # TODO
    # 转换成英文
    data_key = ["今天", "明天", "后天", "大后天"]
    real_dates = get_real_dates(data_key)
    for key in data_key:
        if key in instruction:
            instruction = instruction.replace(key, key + real_dates[key])
    if debug:
        print("new instruction:", instruction)
    logger.info("new instruction:" + str(instruction))

    try:

        img = None

        img = Image.open(image_path)
        patch_size = 14
        merge_size = 2
        min_pixels = 3136
        max_pixels = 12845056
        resized_height, resized_width = smart_resize(
            img.size[1],
            img.size[0],
        )
        img_size = img.size
        height, width = img_size[1], img_size[0]
        img_resize = resize_image(img, resized_width, resized_height)
        base64_image = encode_image_base64(img_resize)
        base64_images = [base64_image]

        hist_step = 3
        T0_act = time.time()
        try:
            # 准备输入
            messages = []
            # 构建 system prompt
            system_prompt = get_agent_system_prompt_for_qwen_vl_en(
                resized_width, resized_height
            )
            messages.append({"role": "system", "content": system_prompt})

            # 构建用户输入
            user_query = f"The user query: {instruction}\nTask progress (You have done the following operation on the current device): "
            if len(summary_history) > 0 and hist_step > 0:
                summary_history_with_step_id = [
                    f"Step{i+1}: {operation}"
                    for i, operation in enumerate(summary_history)
                ]
                user_query += "\n".join(summary_history_with_step_id)
            user_query += "; "

            if tips:
                user_query = f"\nTips: {tips}\n\n" + user_query
            user_content = []
            user_content.append({"type": "text", "text": user_query})
            for base64_image in base64_images:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    }
                )
            messages.append({"role": "user", "content": user_content})
            attempts = 0
            max_attempts = 3
            while attempts < max_attempts:
                completion = n.chat.completions.create(
                    model=model_name,
                    messages=messages,
                )
                output_str = completion.choices[0].message.content

                output_str = "<root>" + output_str + "</root>"
                is_output_valid, message, extracted_data = check_and_extract_xml(
                    output_str
                )
                print(message)
                if is_output_valid:
                    tool_call_str = extracted_data["tool_call"]
                    summary_str = extracted_data["action_description"].strip("\n")
                    if is_valid_json(tool_call_str):
                        tool_call = eval(tool_call_str)
                        if "arguments" in tool_call.keys():
                            tool_call = tool_call["arguments"]
                            if is_valid_tool_call(tool_call, ActionParameters):
                                # print(tool_call)
                                # print(summary_str)
                                output_action = {
                                    "instruction": tool_call,
                                    "summary": summary_str,
                                }
                                break
                            else:
                                attempts += 1
                                print("qwen2.5-vl-7b output format error, retrying..")
                                print(output_str)
                        else:
                            attempts += 1
                            print("qwen2.5-vl-7b output format error, retrying..")
                            print(output_str)
                    else:
                        attempts += 1
                        print("qwen2.5-vl-7b output format error, retrying..")
                        print(output_str)
                else:
                    attempts += 1
                    print("qwen2.5-vl-7b output format error, retrying..")
                    print(output_str)
            if attempts == max_attempts:
                raise Exception(
                    "qwen2.5-vl-7b output format error, max attempts reached"
                )

        except Exception as e:
            output_action = ""
            print(f"act_agent error {e}")

        # 输出推理时间
        T1_act = time.time()
        time_act = T1_act - T0_act
        logger.info("act time:" + str(time_act))

        if debug:
            status = "#" * 50 + " 决策 " + "#" * 50
            print(status)
            for k, v in output_action.items():
                print(f"{k}: {v}")
            print("#" * len(status))
        logger.info("output_action:" + str(output_action))

        # 由于resize过, 所以坐标需要按照resize的比例缩放到原分辨率上
        if output_action["instruction"]["action"] in ["click", "long_press", "swipe"]:
            output_action["instruction"]["coordinate"] = [
                int(
                    output_action["instruction"]["coordinate"][0]
                    * width
                    / resized_width
                ),
                int(
                    output_action["instruction"]["coordinate"][1]
                    * height
                    / resized_height
                ),
            ]
            if output_action["instruction"]["action"] == "swipe":
                output_action["instruction"]["coordinate2"] = [
                    int(
                        output_action["instruction"]["coordinate2"][0]
                        * width
                        / resized_width
                    ),
                    int(
                        output_action["instruction"]["coordinate2"][1]
                        * height
                        / resized_height
                    ),
                ]
        step_json = {
            "episode_id": episode_id,
            "step_id": step_id,
            "instruction": instruction,
            "image_path": image_path,
            "Operation": output_action["summary"],
            "Action": output_action["instruction"],
        }

        sqe_json[-1]["Operation"] = step_json["Operation"]
        sqe_json[-1]["Action"] = step_json["Action"]

    except Exception as e:
        print(f"agent infer error: {e}")
        return sqe_json

    return sqe_json


def execute_app_action(
    action_parameter_ori: ActionParameters,
    ratio: float = None,
    action_description: str = None,
) -> None:
    # 进行操作之后等待的秒数
    click_wait_time = 3  # 点击
    swipe_wait_time = 3  # 滑动
    input_wait_time = 3  # 输入 
    back_wait_time = 3  # 回退
    enter_wait_time = 3  # 回车
    homepage_wait_time = 3  # 主页
    long_press_wait_time = 3  # 长按
    menu_wait_time = 5  # 菜单
    open_wait_time = 5  # 打开app
    # 对坐标进行还原处理
    action_parameter = copy.deepcopy(action_parameter_ori)

    if action_parameter.coordinate:
        action_parameter.coordinate = (
            action_parameter.coordinate[0] / ratio,
            action_parameter.coordinate[1] / ratio,
        )
    if action_parameter.coordinate2:
        action_parameter.coordinate2 = (
            action_parameter.coordinate2[0] / ratio,
            action_parameter.coordinate2[1] / ratio,
        )

    if action_parameter.action == ActionEnum.click:
        print(f"Trying to click element, coordinate: {action_parameter.coordinate}.")
        controller.tap(
            action_parameter.coordinate[0],
            action_parameter.coordinate[1],
        )
        if action_description and "open" in action_description.lower():
            time.sleep(open_wait_time)
        else:
            time.sleep(click_wait_time)
        print("Clicked...")

    elif action_parameter.action == ActionEnum.swipe:
        print("Trying to swipe.")
        controller.slide(
            action_parameter.coordinate[0],
            action_parameter.coordinate[1],
            action_parameter.coordinate2[0],
            action_parameter.coordinate2[1],
        )
        time.sleep(swipe_wait_time)
        print("Swiped...")

    elif action_parameter.action == ActionEnum.type_action:
        print(f"Trying to input text: {action_parameter.text}.")
        controller.type(action_parameter.text)
        time.sleep(input_wait_time)
        print(f"Input done...")

    elif action_parameter.action == ActionEnum.key:
        print(f"Trying to do key action.")
        controller.keyevent(action_parameter.text)
        print(f"Key action done")
    elif action_parameter.action == ActionEnum.long_press:
        print(
            f"Trying to long press element, coordinate: {action_parameter.coordinate}."
        )
        controller.long_press(
            action_parameter.coordinate[0],
            action_parameter.coordinate[1],
            action_parameter.time * 1000,
        )
        time.sleep(long_press_wait_time + action_parameter.time)
        print("Long Pressed...")
    elif action_parameter.action == ActionEnum.system_button:
        print(
            f"Trying to system button action, button type: {action_parameter.button}."
        )
        if action_parameter.button == ButtonEnum.Back:
            controller.back()
            time.sleep(back_wait_time)
        elif action_parameter.button == ButtonEnum.Home:
            controller.home()
            time.sleep(homepage_wait_time)
        elif action_parameter.button == ButtonEnum.Delete:
            pass
        elif action_parameter.button == ButtonEnum.Enter:
            controller.enter()
            time.sleep(enter_wait_time)
        elif action_parameter.button == ButtonEnum.Menu:
            controller.menu()
            time.sleep(menu_wait_time)
        else:
            raise ValueError("Unknown system button type!")
        print(f"System button action done, button type: {action_parameter.button}...")
    elif action_parameter.action == ActionEnum.wait:
        print(f"Waiting for {action_parameter.time} seconds.")
        time.sleep(action_parameter.time)
        print("End Waiting...")
    elif action_parameter.action == ActionEnum.terminate:
        pass
    elif action_parameter.action == ActionEnum.open:
        print(f"Trying to open {action_parameter.text}.")
        controller.open_app(action_parameter.text)
        time.sleep(open_wait_time)
        print(f"{action_parameter.text} opened...")
    else:
        raise ValueError("Unknown action type!")


def path_search(
    instruction: str,
    client: OpenAI,
    model_name: str,
    data,
    episode_id,
    max_iter=30,
    time_gap=8,
    max_edge=1280,
):

    screenshot = f"{data}/{episode_id}/"
    os.makedirs(screenshot, exist_ok=True)

    iter = 0
    sqe_json = []

    while iter <= max_iter:

        status = "#" * 50 + f" 第{iter}轮 " + "#" * 50
        print("\n" + status)

        # 1. 获取截图
        screenshot_file = screenshot + f"{episode_id}_{iter}.jpg"

        T0 = time.time()
        width, height, ratio = controller.get_screenshot(
            iter, screenshot_file, max_edge
        )
        T1 = time.time()
        time_tmp = T1 - T0
        if debug:
            print("screenshot time:%fs" % (time_tmp))

        image_path = screenshot_file

        inp_json = {
            "episode_id": episode_id,
            "step_id": iter,
            "instruction": instruction,
            "image_path": image_path,
            "Operation": "",
            "Action": "",
        }
        sqe_json.append(inp_json)

        # 2. 推理
        T0 = time.time()
        sqe_json = model_agent_infer(sqe_json, client, model_name)
        T1 = time.time()
        time_tmp = T1 - T0
        if debug:
            print("inference time:%fs" % (time_tmp))

        iter += 1

        # 3. 执行
        action_parameter = ActionParameters(**sqe_json[-1]["Action"])
        if action_parameter.action == ActionEnum.terminate:
            print("Task Completed.")
            break
        else:
            execute_app_action(action_parameter, ratio, sqe_json[-1]["Operation"])

    return sqe_json


def generate_episode_id(length=16):
    # 生成当前时间的字符串，格式为 HH:MM
    current_time = datetime.now().strftime("%H-%M")
    # 生成随机的 episode_id
    characters = string.ascii_letters + string.digits  # 包含字母和数字
    episode_id = "".join(random.choices(characters, k=length))
    # 将时间和 episode_id 连接在一起
    full_id = f"{current_time}_{episode_id}"
    # print("full_id:", full_id)
    return full_id


def is_adb_usable():
    try:
        result = subprocess.run(
            ["adb", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            print("ADB is available. Version: ", result.stdout)
            return True
        else:
            print("ADB is NOT available. Errors: ", result.stderr)
            return False
    except FileNotFoundError:
        print(
            "ADB was not found. Please ensure it is installed and added to the PATH environment variable."
        )
        return False


if __name__ == "__main__":
    # 检查adb是否可用(加入环境变量)
    if not is_adb_usable():
        sys.exit(1)
    # 模型调用
    host = "the host where the model is deployed"
    port = "service port"
    url = f"http://{host}:{port}/v1"
    client = OpenAI(base_url=url, api_key="placeholder")
    model_name = "your LLM name, same as the one in the deployment script"

    # 获取当前日期
    now = datetime.now()
    # 格式化日期为 `YYYY-MM-DD` 格式
    today = now.strftime("%Y-%m-%d")
    root = "data/" + today

    instructions = ["Open Settings", "Open Chrome"]

    final_json = []
    max_iter = 30
    max_edge = 1280
    stop_key = [
        "支付",
        "呼叫",
        "付款",
        "提交订单",
        "提交",
        "导航",
        "立即购买",
        "起送",
        "发送",
        "立即打车",
        "立即预约",
        "点击取号",
    ]  # , "下单"
    time_gap = 3

    for instruction in instructions:
        episode_id = generate_episode_id()
        print("\n" + "#" * 100)
        print("User query:", instruction)
        print("episode_id:", episode_id)
        T0 = time.time()
        try:
            sqe_json = path_search(
                instruction,
                client,
                model_name,
                root,
                episode_id,
                max_iter=max_iter,
                time_gap=time_gap,
                max_edge=max_edge,
            )
        except Exception as e:
            print(f"path_search {e}")
            continue
        final_json.append(sqe_json)
        T1 = time.time()
        time_tmp = T1 - T0
        print("MobileAgent time:%fs" % (time_tmp))
