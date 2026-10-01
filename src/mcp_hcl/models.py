from typing import Literal, get_args, get_origin
from pydantic import BaseModel, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def strict_literals(cls, value):
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                if name in value and get_origin(field.annotation) is Literal:
                    types = {type(v) for v in get_args(field.annotation)}
                    if type(value[name]) not in types:
                        raise ValueError(f'{name} requires its exact JSON literal type')
        return value
