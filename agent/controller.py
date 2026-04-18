import os
import time
import subprocess
import random
import string
from typing import Optional
from PIL import Image


def take_screenshots(
    num_screenshots,
    output_folder,
    crop_y_start,
    crop_y_end,
    slide_y_start,
    slide_y_end,
):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for i in range(num_screenshots):
        command = f"adb shell rm /sdcard/screenshot{i}.png"
        subprocess.run(command, capture_output=True, text=True, shell=True)
        command = f"adb shell screencap -p /sdcard/screenshot{i}.png"
        subprocess.run(command, capture_output=True, text=True, shell=True)
        command = f"adb pull /sdcard/screenshot{i}.png {output_folder}"
        subprocess.run(command, capture_output=True, text=True, shell=True)
        image = Image.open(f"{output_folder}/screenshot{i}.png")
        cropped_image = image.crop((0, crop_y_start, image.width, crop_y_end))
        cropped_image.save(f"{output_folder}/screenshot{i}.png")
        subprocess.run(
            [
                "adb",
                "shell",
                "input",
                "swipe",
                "500",
                str(slide_y_start),
                "500",
                str(slide_y_end),
            ]
        )


def get_screenshot(iter, save_path, max_edge=1280):
    command = f"adb shell screencap -p /sdcard/{iter}_screenshot.png"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    time.sleep(0.3)
    command = f"adb pull /sdcard/{iter}_screenshot.png ./"
    subprocess.run(command, capture_output=True, text=True, shell=True)

    image_path = f"./{iter}_screenshot.png"
    img = Image.open(image_path)
    original_width, original_height = img.size

    # 计算调整后的尺寸，确保长边不超过1280像素
    img_resize = img
    ratio = 0.5
    if max(original_width, original_height) > max_edge:
        if original_width > original_height:
            new_width = max_edge
            new_height = int((max_edge / original_width) * original_height)
        else:
            new_height = max_edge
            new_width = int((max_edge / original_height) * original_width)
        img_resize = img.resize((new_width, new_height)).convert("RGB")

    ratio = new_width / original_width

    img_resize = img_resize.convert("RGB")
    img_resize.save(save_path, "JPEG")
    os.remove(image_path)

    return img_resize.size[0], img_resize.size[1], ratio


def get_keyboard(adb_path):
    command = adb_path + " shell dumpsys input_method"
    process = subprocess.run(
        command, capture_output=True, text=True, shell=True, encoding="utf-8"
    )
    output = process.stdout.strip()
    for line in output.split("\n"):
        if "mInputShown" in line:
            if "mInputShown=true" in line:

                for line in output.split("\n"):
                    if "hintText" in line:
                        hintText = line.split("hintText=")[-1].split(" label")[0]
                        break

                return True, hintText
            elif "mInputShown=false" in line:
                return False, None


def tap(x, y, device_id: Optional[str] = None):
    if device_id:
        command = f"adb -s {device_id} shell input tap {x} {y}"
    else:
        command = f"adb shell input tap {x} {y}"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def type(text, device_id: Optional[str] = None):
    text = text.replace("\\n", "_").replace("\n", "_")

    adb_path = "adb"

    # adb prefix 处理
    def cmd_prefix():
        if device_id:
            return f"{adb_path} -s {device_id}"
        else:
            return f"{adb_path}"

    # 切换输入法
    command = cmd_prefix() + " shell ime set com.android.adbkeyboard/.AdbIME"
    subprocess.run(command, capture_output=True, text=True, shell=True)

    # 删除一个字符
    command = cmd_prefix() + " shell input keyevent 67"
    subprocess.run(command, capture_output=True, text=True, shell=True)

    # 移动到文本末尾
    command = cmd_prefix() + " shell input keyevent KEYCODE_MOVE_END"
    subprocess.run(command, capture_output=True, text=True, shell=True)

    max_text_len = 15
    for i in range(max_text_len):
        # 单个字符删除
        command = cmd_prefix() + " shell input keyevent 67"
        subprocess.run(command, capture_output=True, text=True, shell=True)

    # 移动到文本开头
    command = cmd_prefix() + " shell input keyevent KEYCODE_MOVE_HOME"
    subprocess.run(command, capture_output=True, text=True, shell=True)

    # 避免过快输入（KEYCODE_SPACE = 62）
    command = cmd_prefix() + " shell input keyevent 62"
    subprocess.run(command, capture_output=True, text=True, shell=True)

    for char in text:
        if char == " ":
            command = cmd_prefix() + " shell input text %s"
            subprocess.run(command, capture_output=True, text=True, shell=True)
        elif char == "_":
            command = cmd_prefix() + " shell input keyevent 66"
            subprocess.run(command, capture_output=True, text=True, shell=True)
        elif "a" <= char <= "z" or "A" <= char <= "Z" or char.isdigit():
            command = cmd_prefix() + f" shell input text {char}"
            subprocess.run(command, capture_output=True, text=True, shell=True)
        elif char in "-.,!?@'°/:;()":
            command = cmd_prefix() + f' shell input text "{char}"'
            subprocess.run(command, capture_output=True, text=True, shell=True)
        else:
            command = (
                cmd_prefix()
                + f' shell am broadcast -a ADB_INPUT_TEXT --es msg "{char}"'
            )
            subprocess.run(command, capture_output=True, text=True, shell=True)


def slide(x1, y1, x2, y2, device_id: Optional[str] = None, duration: int = 500):
    if device_id:
        command = f"adb -s {device_id} shell input swipe {x1} {y1} {x2} {y2} {duration}"
    else:
        command = f"adb shell input swipe {x1} {y1} {x2} {y2} {duration}"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def back(device_id: Optional[str] = None):
    if device_id:
        command = f"adb -s {device_id} shell input keyevent 4"
    else:
        command = "adb shell input keyevent 4"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def enter(device_id: Optional[str] = None):
    if device_id:
        command = f"adb -s {device_id} shell input keyevent 66"
    else:
        command = "adb shell input keyevent 66"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def home(device_id: Optional[str] = None):
    if device_id:
        command = f"adb -s {device_id} shell am start -a android.intent.action.MAIN -c android.intent.category.HOME"
    else:
        command = "adb shell am start -a android.intent.action.MAIN -c android.intent.category.HOME"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def long_press(x, y, duration, device_id: Optional[str] = None):
    # duration: 长按持续时间/ms
    if device_id:
        command = f"adb -s {device_id} shell input swipe {x} {y} {x} {y} {duration}"
    else:
        command = f"adb shell input swipe {x} {y} {x} {y} {duration}"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def keyevent(keyevent_name: str, device_id: Optional[str] = None):
    keyevent_name_uppercase = keyevent_name.upper()
    if device_id:
        command = f"adb -s {device_id} shell input keyevent {keyevent_name_uppercase}"
    else:
        command = f"adb shell input keyevent {keyevent_name_uppercase}"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def menu(device_id: Optional[str] = None):
    if device_id:
        keyevent("KEYCODE_MENU", device_id)
    else:
        keyevent("KEYCODE_MENU")
