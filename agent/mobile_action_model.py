from enum import Enum
from pydantic import (
    BaseModel,
    model_validator,
    field_validator,
    Field,
    ConfigDict,
)
from typing import List, Optional


class ActionEnum(str, Enum):
    key = "key"
    click = "click"
    long_press = "long_press"
    swipe = "swipe"
    type_action = "type"  # 避免与 Python 的 type 关键字冲突
    system_button = "system_button"
    wait = "wait"
    terminate = "terminate"
    open = "open"


class ButtonEnum(str, Enum):
    Back = "Back"
    Home = "Home"
    Menu = "Menu"
    Enter = "Enter"
    Delete = "Delete"


class StatusEnum(str, Enum):
    success = "success"
    failure = "failure"


class ActionParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 禁止未知字段，增强安全性

    action: ActionEnum = Field(
        ...,
        description=(
            "The action to perform. Available actions: key, click, long_press, "
            "swipe, type, system_button, wait, terminate, open."
        ),
    )
    coordinate: Optional[List[int]] = Field(
        None,
        description=(
            "(x, y): Coordinates required for click, long_press, and swipe actions."
        ),
    )
    coordinate2: Optional[List[int]] = Field(
        None, description=("(x, y): End coordinates required only for swipe action.")
    )
    text: Optional[str] = Field(
        None, description="Text input for key, type or open actions."
    )
    time: Optional[float] = Field(
        None, description="Duration for long_press or wait actions."
    )
    button: Optional[ButtonEnum] = Field(
        None,
        description="System button (Back, Home, Menu, Enter, Delete) required for system_button action.",
    )
    status: Optional[StatusEnum] = Field(
        None, description="Task status (success/failure) required for terminate action."
    )

    @field_validator("coordinate", "coordinate2")
    def validate_coordinate(cls, v):
        """验证坐标是否为包含两个整数的列表"""
        if v is not None:
            if not isinstance(v, list) or len(v) != 2:
                raise ValueError("Coordinate must be a list of two integers")
            if not all(isinstance(num, int) for num in v):
                raise ValueError("Coordinates must be integers")
        return v

    @model_validator(mode="after")
    def validate_action_requirements(self) -> "ActionParameters":
        action = self.action
        required = {
            ActionEnum.key: ["text"],
            ActionEnum.click: ["coordinate"],
            ActionEnum.long_press: ["coordinate", "time"],
            ActionEnum.swipe: ["coordinate", "coordinate2"],
            ActionEnum.type_action: ["text"],
            ActionEnum.system_button: ["button"],
            ActionEnum.wait: ["time"],
            ActionEnum.terminate: ["status"],
            ActionEnum.open: ["text"],
        }.get(action, [])

        # 检查必需字段是否存在
        for field in required:
            if getattr(self, field) is None:
                raise ValueError(f"action={action.value} requires '{field}'")

        # 检查不允许的字段是否存在
        allowed_fields = set(required) | {"action"}
        for field in self.model_fields.keys():
            if field not in allowed_fields and getattr(self, field) is not None:
                raise ValueError(f"action={action.value} cannot have field '{field}'")

        return self

    def to_dict(self):
        """
        根据当前 action 类型，返回仅包含必要参数的字典。
        示例输出:
        {"action": "swipe", "coordinate": [1378, 1122], "coordinate2": [0, 1090]}
        """
        action = self.action
        required_fields = {
            ActionEnum.key: ["text"],
            ActionEnum.click: ["coordinate"],
            ActionEnum.long_press: ["coordinate", "time"],
            ActionEnum.swipe: ["coordinate", "coordinate2"],
            ActionEnum.type_action: ["text"],
            ActionEnum.system_button: ["button"],
            ActionEnum.wait: ["time"],
            ActionEnum.terminate: ["status"],
            ActionEnum.open: ["text"],
        }.get(action, [])
        result = {"action": action.value}
        for field in required_fields:
            value = getattr(self, field)
            if value is not None:  # 经过验证器确保非空，但保留判断增强健壮性
                result[field] = value
        return result


if __name__ == "__main__":
    params = ActionParameters(
        action="system_button",
        button="Back",
    )
    print(params.model_dump())
