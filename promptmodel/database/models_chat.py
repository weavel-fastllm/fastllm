from enum import Enum
import datetime
import json

from uuid import uuid4
from peewee import (
    CharField,
    DateTimeField,
    IntegerField,
    ForeignKeyField,
    BooleanField,
    UUIDField,
    TextField,
    AutoField,
    FloatField,
    Check,
)

from promptmodel.database.config import BaseModel
from promptmodel.utils.enums import ModelVersionStatus, ParsingType


class JSONField(TextField):
    def db_value(self, value):
        return json.dumps(value)

    def python_value(self, value):
        return json.loads(value)


class ChatModel(BaseModel):
    uuid = UUIDField(unique=True, default=uuid4)
    created_at = DateTimeField(default=datetime.datetime.now)
    project_uuid = UUIDField()
    name = CharField()
    used_in_code = BooleanField(default=True)
    is_deployed = BooleanField(
        default=False
    )  # mark if the module is pushed to the cloud


class ChatModelVersion(BaseModel):
    uuid = UUIDField(unique=True, default=uuid4)
    created_at = DateTimeField(default=datetime.datetime.now)
    from_uuid = UUIDField(null=True)
    chat_model_uuid = ForeignKeyField(
        ChatModel,
        field=ChatModel.uuid,
        backref="versions",
        on_delete="CASCADE",
    )
    status = CharField(
        constraints=[
            Check(
                f"status IN ('{ModelVersionStatus.BROKEN.value}', '{ModelVersionStatus.WORKING.value}', '{ModelVersionStatus.CANDIDATE.value}')"
            )
        ]
    )
    model = CharField()
    version = IntegerField(null=True)
    is_published = BooleanField(default=False)
    is_deployed = BooleanField(default=False)
    system_prompt = JSONField(null=True, default={})
    functions = JSONField(default=[])


class ChatLog(BaseModel):
    id = AutoField()
    created_at = DateTimeField(default=datetime.datetime.now)
    chat_uuid = UUIDField(unique=False)
    version_uuid = ForeignKeyField(
        ChatModelVersion,
        field=ChatModelVersion.uuid,
        backref="run_logs",
        on_delete="CASCADE",
    )
    role = CharField(null=True, default=None)
    content = CharField(null=True, default=None)
    function_call = JSONField(null=True, default=None)
    run_from_deployment = BooleanField(default=False)
    function_call = JSONField(null=True, default={})


# class DeployedChatModel(BaseModel):
#     uuid = UUIDField(unique=True, default=uuid4)
#     name = CharField()


# class DeployedChatModelVersion(BaseModel):
#     uuid = UUIDField(unique=True, default=uuid4)
#     from_uuid = UUIDField(null=True)
#     chat_model_uuid = ForeignKeyField(
#         DeployedChatModel,
#         field=DeployedChatModel.uuid,
#         backref="versions",
#         on_delete="CASCADE",
#     )
#     model = CharField()
#     is_published = BooleanField(default=False)
#     is_ab_test = BooleanField(default=False)
#     ratio = FloatField(null=True)
#     system_prompt = JSONField(null=True, default={})
#     functions = JSONField(default=[])