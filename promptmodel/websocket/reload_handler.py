import os
import sys
import importlib
from typing import Any, Dict, List
from threading import Timer
from rich import print
from watchdog.events import FileSystemEventHandler
from playhouse.shortcuts import model_to_dict

from promptmodel.apis.base import APIClient
from promptmodel.utils.config_utils import read_config, upsert_config
from promptmodel.utils import logger
from promptmodel import DevApp
from promptmodel.database.models import *
from promptmodel.database.crud import (
    update_samples,
    update_prompt_model_uuid,
    update_chat_model_uuid,
)
from promptmodel.types.enums import (
    ModelVersionStatus,
    ChangeLogAction,
)
from promptmodel.websocket.websocket_client import DevWebsocketClient


class CodeReloadHandler(FileSystemEventHandler):
    def __init__(
        self,
        _devapp_filename: str,
        _instance_name: str,
        dev_websocket_client: DevWebsocketClient,
    ):
        self._devapp_filename: str = _devapp_filename
        self.devapp_instance_name: str = _instance_name
        self.dev_websocket_client: DevWebsocketClient = (
            dev_websocket_client  # save dev_websocket_client instance
        )
        self.timer = None

    def on_modified(self, event):
        """Called when a file or directory is modified."""
        if event.src_path.endswith(".py"):
            if self.timer:
                self.timer.cancel()
            # reload modified file & main file
            self.timer = Timer(0.5, self.reload_code, args=(event.src_path,))
            self.timer.start()

    def reload_code(self, modified_file_path: str):
        print(
            f"[violet]promptmodel:dev:[/violet]  Reloading {self._devapp_filename} module due to changes..."
        )
        relative_modified_path = os.path.relpath(modified_file_path, os.getcwd())
        # Reload the devapp module
        module_name = relative_modified_path.replace("./", "").replace("/", ".")[
            :-3
        ]  # assuming the file is in the PYTHONPATH

        if module_name in sys.modules:
            module = sys.modules[module_name]
            importlib.reload(module)

        reloaded_module = importlib.reload(sys.modules[self._devapp_filename])
        print(
            f"[violet]promptmodel:dev:[/violet]  {self._devapp_filename} module reloaded successfully."
        )

        new_devapp_instance: DevApp = getattr(
            reloaded_module, self.devapp_instance_name
        )

        new_prompt_model_name_list = new_devapp_instance._get_prompt_model_name_list()
        old_prompt_model_name_list = (
            self.dev_websocket_client._devapp._get_prompt_model_name_list()
        )

        new_chat_model_name_list = new_devapp_instance._get_chat_model_name_list()
        old_chat_model_name_list = (
            self.dev_websocket_client._devapp._get_chat_model_name_list()
        )

        # Update localDB prompt_model.used_in_code=False which diappeared in code
        removed_name_list = list(
            set(old_prompt_model_name_list) - set(new_prompt_model_name_list)
        )
        PromptModel.update(used_in_code=False).where(
            PromptModel.name.in_(removed_name_list)
        ).execute()

        # Update localDB chat_model.used_in_code=False which diappeared in code
        removed_name_list = list(
            set(old_chat_model_name_list) - set(new_chat_model_name_list)
        )
        ChatModel.update(used_in_code=False).where(
            ChatModel.name.in_(removed_name_list)
        ).execute()

        # Update localDB prompt_model.used_in_code True which created newly
        # TODO: Use more specific API
        config = read_config()
        org = config["dev_branch"]["org"]
        project = config["dev_branch"]["project"]
        project_status = APIClient.execute(
            method="GET",
            path="/pull_project",
            params={"project_uuid": project["uuid"]},
        ).json()

        changelogs = APIClient.execute(
            method="GET",
            path="/get_changelog",
            params={
                "project_uuid": project["uuid"],
                "local_project_version": config["dev_branch"]["project_version"],
                "levels": [1, 2],
            },
        ).json()
        # IF used_in_code=False 인 name=name 이 있을 경우, used_in_code=True
        update_by_changelog_for_reload(
            changelogs=changelogs,
            project_status=project_status,
            local_code_prompt_model_name_list=new_prompt_model_name_list,
            local_code_chat_model_name_list=new_chat_model_name_list,
        )

        PromptModel.update(used_in_code=True).where(
            PromptModel.name.not_in(old_prompt_model_name_list)
        ).execute()

        ChatModel.update(used_in_code=True).where(
            ChatModel.name.not_in(old_chat_model_name_list)
        ).execute()

        # create prompt_models in local DB
        db_prompt_model_list = [
            model_to_dict(x, recurse=False) for x in [PromptModel.select()]
        ]
        db_prompt_model_name_list = [x["name"] for x in db_prompt_model_list]
        only_in_local_names = list(
            set(new_prompt_model_name_list) - set(db_prompt_model_name_list)
        )
        only_in_local_prompt_models = [
            {"name": x, "project_uuid": project["uuid"]} for x in only_in_local_names
        ]
        PromptModel.insert_many(only_in_local_prompt_models).execute()

        # create chat_models in local DB
        db_chat_model_list = [
            model_to_dict(x, recurse=False) for x in [ChatModel.select()]
        ]
        db_chat_model_name_list = [x["name"] for x in db_chat_model_list]
        only_in_local_names = list(
            set(new_chat_model_name_list) - set(db_chat_model_name_list)
        )
        only_in_local_chat_models = [
            {"name": x, "project_uuid": project["uuid"]} for x in only_in_local_names
        ]
        ChatModel.insert_many(only_in_local_chat_models).execute()

        # update samples in local DB
        update_samples(new_devapp_instance.samples)
        self.dev_websocket_client.update_devapp_instance(new_devapp_instance)


def update_by_changelog_for_reload(
    changelogs: List[Dict],
    project_status: dict,
    local_code_prompt_model_name_list: List[str],
    local_code_chat_model_name_list: List[str],
):
    """Update Local DB by changelog"""
    local_db_prompt_model_list: list = [
        model_to_dict(x, recurse=False) for x in [PromptModel.select()]
    ]  # {"name", "uuid"}
    local_db_chat_model_list: list = [
        model_to_dict(x, recurse=False) for x in [ChatModel.select()]
    ]  # {"name", "uuid"}

    for changelog in changelogs:
        level: int = changelog["level"]
        logs = changelog["logs"]
        if level == 1:
            for log in logs:
                subject = log["subject"]
                action: str = log["action"]
                if subject == "prompt_model":
                    local_db_prompt_model_list = update_prompt_model_changelog(
                        action=action,
                        project_status=project_status,
                        uuid_list=log["identifiers"],
                        local_db_prompt_model_list=local_db_prompt_model_list,
                        local_code_prompt_model_name_list=local_code_prompt_model_name_list,
                    )

                elif subject == "prompt_model_version":
                    local_db_prompt_model_list = update_prompt_model_version_changelog(
                        action=action,
                        project_status=project_status,
                        uuid_list=log["identifiers"],
                        local_db_prompt_model_list=local_db_prompt_model_list,
                        local_code_prompt_model_name_list=local_code_prompt_model_name_list,
                    )

                elif subject == "chat_model":
                    local_db_chat_model_list = update_chat_model_changelog(
                        action=action,
                        project_status=project_status,
                        uuid_list=log["identifiers"],
                        local_db_chat_model_list=local_db_chat_model_list,
                        local_code_chat_model_name_list=local_code_chat_model_name_list,
                    )

                elif subject == "chat_model_version":
                    local_db_chat_model_list = update_chat_model_version_changelog(
                        action=action,
                        project_status=project_status,
                        uuid_list=log["identifiers"],
                        local_db_chat_model_list=local_db_chat_model_list,
                        local_code_chat_model_name_list=local_code_chat_model_name_list,
                    )
                else:
                    pass
            previous_version_levels = changelog["previous_version"].split(".")
            current_version_levels = [
                str(int(previous_version_levels[0]) + 1),
                "0",
                "0",
            ]
            current_version = ".".join(current_version_levels)
        elif level == 2:
            for log in logs:
                subject = log["subject"]
                action: str = log["action"]
                uuid_list: list = log["identifiers"]
                if subject == "prompt_model_version":
                    local_db_prompt_model_list = update_prompt_model_version_changelog(
                        action=action,
                        project_status=project_status,
                        uuid_list=log["identifiers"],
                        local_db_prompt_model_list=local_db_prompt_model_list,
                        local_code_prompt_model_name_list=local_code_prompt_model_name_list,
                    )

                elif subject == "chat_model_version":
                    local_db_chat_model_list = update_chat_model_version_changelog(
                        action=action,
                        project_status=project_status,
                        uuid_list=log["identifiers"],
                        local_db_chat_model_list=local_db_chat_model_list,
                        local_code_chat_model_name_list=local_code_chat_model_name_list,
                    )
                else:
                    pass
            previous_version_levels = changelog["previous_version"].split(".")
            current_version_levels = [
                previous_version_levels[0],
                str(int(previous_version_levels[1]) + 1),
                "0",
            ]
            current_version = ".".join(current_version_levels)
        else:
            previous_version_levels = changelog["previous_version"].split(".")
            current_version_levels = [
                previous_version_levels[0],
                previous_version_levels[1],
                str(int(previous_version_levels[2]) + 1),
            ]
            current_version = ".".join(current_version_levels)

        upsert_config({"project_version": current_version}, section="dev_branch")
    return True


def update_prompt_model_changelog(
    action: ChangeLogAction,
    project_status: dict,
    uuid_list: List[str],
    local_db_prompt_model_list: List[Dict],
    local_code_prompt_model_name_list: List[str],
):
    if action == ChangeLogAction.ADD.value:
        prompt_model_list = [
            x for x in project_status["prompt_models"] if x["uuid"] in uuid_list
        ]
        for prompt_model in prompt_model_list:
            local_db_prompt_model_name_list = [
                x["name"] for x in local_db_prompt_model_list
            ]

            if prompt_model["name"] not in local_db_prompt_model_name_list:
                # IF prompt_model not in Local DB
                if prompt_model["name"] in local_code_prompt_model_name_list:
                    # IF prompt_model in Local Code
                    prompt_model["used_in_code"] = True
                    prompt_model["is_deployed"] = True
                else:
                    prompt_model["used_in_code"] = False
                    prompt_model["is_deployed"] = True

                PromptModel.create(**prompt_model)
            else:
                # Fix UUID of prompt_model
                local_uuid = model_to_dict(
                    PromptModel.get(PromptModel.name == prompt_model["name"]),
                    recurse=False,
                )["uuid"]

                update_prompt_model_uuid(local_uuid, prompt_model["uuid"])

                local_db_prompt_model_list: list = [
                    model_to_dict(x, recurse=False) for x in [PromptModel.select()]
                ]
    else:
        # TODO: add code DELETE, CHANGE, FIX later
        pass

    return local_db_prompt_model_list


def update_prompt_model_version_changelog(
    action: ChangeLogAction,
    project_status: dict,
    uuid_list: List[str],
    local_db_prompt_model_list: List[Dict],
    local_code_prompt_model_name_list: List[str],
) -> List[Dict[str, Any]]:
    local_db_prompt_model_version_list: List[Dict] = []
    for local_db_prompt_model in local_db_prompt_model_list:
        local_db_prompt_model_version_list += [
            model_to_dict(x, recurse=False)
            for x in [
                PromptModelVersion.select()
                .where(
                    PromptModelVersion.prompt_model_uuid
                    == local_db_prompt_model["uuid"]
                )
                .order_by(PromptModelVersion.created_at)
            ]
        ]
    uuid_list = list(
        filter(
            lambda uuid: uuid
            not in [str(x["uuid"]) for x in local_db_prompt_model_version_list],
            uuid_list,
        )
    )
    if action == ChangeLogAction.ADD.value:
        # find prompt_model_version in project_status['prompt_model_versions'] where uuid in uuid_list
        prompt_model_version_list_to_update = [
            x for x in project_status["prompt_model_versions"] if x["uuid"] in uuid_list
        ]
        # check if prompt_model_version['name'] is in local_code_prompt_model_list

        # find prompts and run_logs to update
        prompts_to_update = [
            x for x in project_status["prompts"] if x["version_uuid"] in uuid_list
        ]
        run_logs_to_update = [
            x for x in project_status["run_logs"] if x["version_uuid"] in uuid_list
        ]

        for prompt_model_version in prompt_model_version_list_to_update:
            prompt_model_version["status"] = ModelVersionStatus.CANDIDATE.value

        PromptModelVersion.insert_many(prompt_model_version_list_to_update).execute()
        Prompt.insert_many(prompts_to_update).execute()
        RunLog.insert_many(run_logs_to_update).execute()

        # local_db_prompt_model_list += [{"name" : x['name'], "uuid" : x['uuid']} for x in prompt_model_version_list_to_update]
        return local_db_prompt_model_list
    else:
        pass


def update_chat_model_changelog(
    action: ChangeLogAction,
    project_status: dict,
    uuid_list: List[str],
    local_db_chat_model_list: List[Dict],
    local_code_chat_model_name_list: List[str],
):
    if action == ChangeLogAction.ADD.value:
        chat_model_list = [
            x for x in project_status["chat_models"] if x["uuid"] in uuid_list
        ]
        for chat_model in chat_model_list:
            local_db_chat_model_name_list = [
                x["name"] for x in local_db_chat_model_list
            ]

            if chat_model["name"] not in local_db_chat_model_name_list:
                # IF chat_model not in Local DB
                if chat_model["name"] in local_code_chat_model_name_list:
                    # IF chat_model in Local Code
                    chat_model["used_in_code"] = True
                    chat_model["is_deployed"] = True
                else:
                    chat_model["used_in_code"] = False
                    chat_model["is_deployed"] = True
                ChatModel.create(**chat_model)
            else:
                # Fix UUID of chat_model
                local_uuid = model_to_dict(
                    ChatModel.get(ChatModel.name == chat_model["name"]),
                    recurse=False,
                )["uuid"]

                update_chat_model_uuid(local_uuid, chat_model["uuid"])

                local_db_chat_model_list: list = [
                    model_to_dict(x, recurse=False) for x in [ChatModel.select()]
                ]
    else:
        # TODO: add code DELETE, CHANGE, FIX later
        pass

    return local_db_chat_model_list


def update_chat_model_version_changelog(
    action: ChangeLogAction,
    project_status: dict,
    uuid_list: List[str],
    local_db_chat_model_list: List[Dict],
    local_code_chat_model_name_list: List[str],
) -> List[Dict[str, Any]]:
    local_db_chat_model_version_list: List[Dict] = []
    for local_db_chat_model in local_db_chat_model_list:
        local_db_chat_model_version_list += [
            model_to_dict(x, recurse=False)
            for x in [
                ChatModelVersion.select()
                .where(ChatModelVersion.chat_model_uuid == local_db_chat_model["uuid"])
                .order_by(ChatModelVersion.created_at)
            ]
        ]

    uuid_list = list(
        filter(
            lambda uuid: uuid
            not in [str(x["uuid"]) for x in local_db_chat_model_version_list],
            uuid_list,
        )
    )
    if action == ChangeLogAction.ADD.value:
        # find chat_model_version in project_status['chat_model_versions'] where uuid in uuid_list
        chat_model_version_list_to_update = [
            x for x in project_status["chat_model_versions"] if x["uuid"] in uuid_list
        ]
        # check if chat_model_version['name'] is in local_code_chat_model_list

        for chat_model_version in chat_model_version_list_to_update:
            chat_model_version["status"] = ModelVersionStatus.CANDIDATE.value

        ChatModelVersion.insert_many(chat_model_version_list_to_update).execute()

        # local_db_chat_model_list += [{"name" : x['name'], "uuid" : x['uuid']} for x in chat_model_version_list_to_update]
        return local_db_chat_model_list
    else:
        pass
