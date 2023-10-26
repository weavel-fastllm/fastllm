import inspect
import asyncio
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)
from rich import print
from litellm import RateLimitManager, ModelResponse
from promptmodel.llms.llm import LLM
from promptmodel.utils import logger
from promptmodel.utils.config_utils import read_config, upsert_config
from promptmodel.utils.prompt_util import fetch_prompts
from promptmodel.utils.output_utils import update_dict
from promptmodel.apis.base import APIClient, AsyncAPIClient
from promptmodel.utils.types import LLMResponse, LLMStreamResponse

class LLMProxy(LLM):
    def __init__(
        self, name: str, rate_limit_manager: Optional[RateLimitManager] = None
    ):
        super().__init__(rate_limit_manager)
        self._name = name

    def _wrap_gen(self, gen: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(inputs: Dict[str, Any], **kwargs):
            prompts, version_details = asyncio.run(fetch_prompts(self._name))
            call_args = self._prepare_call_args(prompts, version_details, inputs, kwargs)
            # Call the generator with the arguments
            stream_response : Generator[LLMStreamResponse] = gen(**call_args)

            raw_response = None
            dict_cache = {}  # to store aggregated dictionary values
            string_cache = ""  # to store aggregated string values
            error_occurs = False
            error_log = None
            for item in stream_response:
                if item.api_response:
                    raw_response = item.api_response
                if item.parsed_outputs:
                    dict_cache = update_dict(dict_cache, item.parsed_outputs)
                if item.raw_output:
                    string_cache += item.raw_output
                if item.error and not error_occurs:
                    error_occurs = True
                    error_log = item.error_log
                yield item

            # add string_cache in model_response
            if "message" not in raw_response.choices[0]:
                raw_response.choices[0]["message"] = {}
            if "content" not in raw_response.choices[0]["message"]:
                raw_response.choices[0]["message"]["content"] = string_cache
                raw_response.choices[0]["message"]["role"] = "assistant"
            
            metadata = {
                "error_occurs" : error_occurs,
                "error_log" : error_log,
            }
            self._log_to_cloud(version_details['uuid'], inputs, raw_response, dict_cache, metadata)

        return wrapper

    def _wrap_async_gen(self, async_gen: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(inputs: Dict[str, Any], **kwargs):
            prompts, version_details = await fetch_prompts(self._name)
            call_args = self._prepare_call_args(prompts, version_details, inputs, kwargs)

            # Call async_gen with the arguments
            stream_response : AsyncGenerator[LLMStreamResponse]= async_gen(**call_args)
            
            raw_response = None
            dict_cache = {}  # to store aggregated dictionary values
            string_cache = ""  # to store aggregated string values
            error_occurs = False
            error_log = None
            raw_response : ModelResponse = None
            async for item in stream_response:
                if item.api_response:
                    raw_response = item.api_response
                if item.parsed_outputs:
                    dict_cache = update_dict(dict_cache, item.parsed_outputs)
                if item.raw_output:
                    string_cache += item.raw_output
                if item.error and not error_occurs:
                    error_occurs = True
                    error_log = item.error_log
                yield item
            
            # add string_cache in model_response
            if "message" not in raw_response.choices[0]:
                raw_response.choices[0]["message"] = {}
            if "content" not in raw_response.choices[0]["message"]:
                raw_response.choices[0]["message"]["content"] = string_cache
                raw_response.choices[0]["message"]["role"] = "assistant"
            
            metadata = {
                "error_occurs" : error_occurs,
                "error_log" : error_log,
            }
            self._log_to_cloud(version_details['uuid'], inputs, raw_response, dict_cache, metadata)
            
            # raise Exception("error_log")
            
        return wrapper

    def _wrap_method(self, method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(inputs: Dict[str, Any], **kwargs):
            prompts, version_details = asyncio.run(fetch_prompts(self._name))
            call_args = self._prepare_call_args(prompts, version_details, inputs, kwargs)
            
            # Call the method with the arguments
            llm_response : LLMResponse = method(**call_args)
            error_occurs = llm_response.error
            error_log = llm_response.error_log
            metadata = {
                "error_occurs" : error_occurs,
                "error_log" : error_log,
            }
            
            if llm_response.parsed_outputs:
                self._log_to_cloud(version_details['uuid'], inputs, llm_response.api_response, llm_response.parsed_outputs, metadata)
            else:
                self._log_to_cloud(version_details['uuid'], inputs, llm_response.api_response, {}, metadata)
            return llm_response

        return wrapper

    def _wrap_async_method(self, method: Callable[..., Any]) -> Callable[..., Any]:
        async def async_wrapper(inputs: Dict[str, Any], **kwargs):
            prompts, version_details = await fetch_prompts(self._name) # messages, model, uuid = self._fetch_prompts()
            call_args = self._prepare_call_args(prompts, version_details, inputs, kwargs)

            # Call the method with the arguments
            llm_response : LLMResponse = await method(**call_args)
            error_occurs = llm_response.error
            error_log = llm_response.error_log
            metadata = {
                "error_occurs" : error_occurs,
                "error_log" : error_log,
            }
            
            if llm_response.parsed_outputs:
                self._log_to_cloud(version_details['uuid'], inputs, llm_response.api_response, llm_response.parsed_outputs, metadata)
            else:
                self._log_to_cloud(version_details['uuid'], inputs, llm_response.api_response, {}, metadata)
            return llm_response
        return async_wrapper

    def _prepare_call_args(
        self,
        prompts: List[Dict[str, str]],
        version_detail: Dict[str, Any],
        inputs: Dict[str, Any],
        kwargs,
    ):
        stringified_inputs = {key: str(value) for key, value in inputs.items()}
        messages = [
            {
                "content": prompt["content"].format(**stringified_inputs),
                "role": prompt["role"],
            }
            for prompt in prompts
        ]
        call_args = {
            "messages": messages,
            "model": version_detail['model'] if version_detail else None,
            "parsing_type": version_detail['parsing_type'] if version_detail else None,
            "output_keys": version_detail['output_keys'] if version_detail else None,
        }
        if call_args["parsing_type"] is None:
            del call_args["parsing_type"]
            del call_args["output_keys"]

        if "function_list" in kwargs:
            call_args["function_list"] = kwargs["function_list"]
        # call_args = {"messages", "model", Optional["function_list"], Optional["parsing_type"], Optional["output_keys"]}
        return call_args

    def _log_to_cloud(
        self,
        version_uuid: str,
        inputs: dict,
        api_response: ModelResponse,
        parsed_outputs: dict,
        metadata: dict
    ):
        # Log to cloud
        # logging if only status = deployed
        config = read_config()
        if "dev_branch" in config and (
            config["dev_branch"]["initializing"] or config["dev_branch"]["online"]
        ):
            return

        api_response_dict = api_response.to_dict_recursive()
        api_response_dict.update({"response_ms": api_response.response_ms})
        res = asyncio.run(
            AsyncAPIClient.execute(
                method="POST",
                path="/log_deployment_run",
                params={
                    "version_uuid": version_uuid,
                },
                json={
                    "inputs": inputs,
                    "api_response": api_response_dict,
                    "parsed_outputs": parsed_outputs,
                    "metadata": metadata,
                },
                use_cli_key=False,
            )
        )
        if res.status_code != 200:
            print(f"[red]Failed to log to cloud: {res.json()}[/red]")
        return

    def run(self, inputs: Dict[str, Any] = {}) -> str:
        return self._wrap_method(super().run)(inputs)

    def arun(self, inputs: Dict[str, Any] = {}) -> str:
        return self._wrap_async_method(super().arun)(inputs)

    # def run_function_call(self, inputs: Dict[str, Any] = {}) -> Tuple[Any, Any]:
    #     return self._wrap_method(super().run_function_call)(inputs)

    # def arun_function_call(self, inputs: Dict[str, Any] = {}) -> Tuple[Any, Any]:
    #     return self._wrap_async_method(super().arun_function_call)(inputs)

    def stream(self, inputs: Dict[str, Any] = {}) -> Generator[LLMStreamResponse]:
        return self._wrap_gen(super().stream)(inputs)

    def astream(
        self, inputs: Optional[Dict[str, Any]] = {}
    ) -> AsyncGenerator[LLMStreamResponse]:
        return self._wrap_async_gen(super().astream)(inputs)

    def run_and_parse(
        self,
        inputs: Dict[str, Any] = {},
    ) -> LLMResponse:
        return self._wrap_method(super().run_and_parse)(inputs)

    def arun_and_parse(
        self,
        inputs: Dict[str, Any] = {},
    ) -> LLMResponse:
        return self._wrap_async_gen(super().arun_and_parse)(inputs)

    def stream_and_parse(
        self,
        inputs: Dict[str, Any] = {},
    ) -> Generator[LLMStreamResponse]:
        return self._wrap_gen(super().stream_and_parse)(inputs)

    def astream_and_parse(
        self,
        inputs: Dict[str, Any] = {},
    ) -> AsyncGenerator[LLMStreamResponse]:
        return self._wrap_async_gen(super().astream_and_parse)(inputs)

    # def run_and_parse_function_call(
    #     self,
    #     inputs: Dict[str, Any] = {},
    #     function_list: List[Callable[..., Any]] = [],
    # ) -> Generator[str, None, None]:
    #     return self._wrap_method(super().run_and_parse_function_call)(
    #         inputs, function_list
    #     )

    # def arun_and_parse_function_call(
    #     self,
    #     inputs: Dict[str, Any] = {},
    #     function_list: List[Callable[..., Any]] = [],
    # ) -> Generator[str, None, None]:
    #     return self._wrap_async_method(super().arun_and_parse_function_call)(
    #         inputs, function_list
    #     )

    # def astream_and_parse_function_call(
    #     self,
    #     inputs: Dict[str, Any] = {},
    #     function_list: List[Callable[..., Any]] = [],
    # ) -> AsyncGenerator[str, None]:
    #     return self._wrap_async_gen(super().astream_and_parse_function_call)(
    #         inputs, function_list
    #     )
