import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from typing import Generator, AsyncGenerator, Dict, List, Any, Optional
from litellm import ModelResponse

from promptmodel.llms.llm import LLM, ParseResult
from promptmodel.llms.llm_proxy import LLMProxy
from promptmodel.types.response import LLMResponse, LLMStreamResponse
from promptmodel.types.enums import ParsingType
from promptmodel import ChatModel, DevClient
from promptmodel.dev_app import ChatModelInterface, ChatModelInterface
from promptmodel.chatmodel import RegisteringMeta

client = DevClient()


def test_find_client(mocker):
    pm = ChatModel("test")
    assert client.chat_models == [ChatModelInterface(name="test")]


def test_get_prompts(mocker, mock_fetch_chat_model):
    fetch_chat_model = mocker.patch(
        "promptmodel.chatmodel.LLMProxy.fetch_chat_model", mock_fetch_chat_model
    )
    # mock registering_meta
    mocker.patch("promptmodel.chatmodel.RegisteringMeta", MagicMock())
    chat_model = ChatModel("test")
    assert len(client.chat_models) == 1
    prompts = chat_model.get_prompts()
    assert len(prompts) == 1


def test_add_messages(
    mocker,
    mock_async_chat_log_to_cloud: AsyncMock,
):
    pass


def test_run(
    mocker,
    mock_fetch_chat_log: AsyncMock,
    mock_fetch_chat_model: AsyncMock,
    mock_async_chat_log_to_cloud: AsyncMock,
):
    fetch_chat_log = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_log", mock_fetch_chat_log
    )
    fetch_chat_model = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_model", mock_fetch_chat_model
    )

    async_chat_log_to_cloud = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy._async_chat_log_to_cloud",
        mock_async_chat_log_to_cloud,
    )

    mocker.patch("promptmodel.chatmodel.RegisteringMeta", MagicMock())
    chat_model = ChatModel("test", session_uuid="testuuid")

    res: LLMResponse = chat_model.run()
    print(res.api_response.model_dump())

    fetch_chat_log.assert_called_once()
    fetch_chat_model.assert_called_once()
    async_chat_log_to_cloud.assert_called_once()

    assert res.raw_output is not None
    assert res.error is None or res.error is False
    assert res.api_response is not None
    assert res.parsed_outputs is None


@pytest.mark.asyncio
async def test_arun(
    mocker,
    mock_fetch_chat_log: AsyncMock,
    mock_fetch_chat_model: AsyncMock,
    mock_async_chat_log_to_cloud: AsyncMock,
):
    fetch_chat_log = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_log", mock_fetch_chat_log
    )
    fetch_chat_model = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_model", mock_fetch_chat_model
    )

    async_chat_log_to_cloud = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy._async_chat_log_to_cloud",
        mock_async_chat_log_to_cloud,
    )
    mocker.patch("promptmodel.chatmodel.RegisteringMeta", MagicMock())
    chat_model = ChatModel("test", session_uuid="testuuid")

    res: LLMResponse = await chat_model.arun()
    print(res.api_response.model_dump())

    fetch_chat_log.assert_called_once()
    fetch_chat_model.assert_called_once()
    async_chat_log_to_cloud.assert_called_once()

    assert res.raw_output is not None
    assert res.error is None or res.error is False
    assert res.api_response is not None
    assert res.parsed_outputs is None


def test_stream(
    mocker,
    mock_fetch_chat_log: AsyncMock,
    mock_fetch_chat_model: AsyncMock,
    mock_async_chat_log_to_cloud: AsyncMock,
):
    fetch_chat_log = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_log", mock_fetch_chat_log
    )
    fetch_chat_model = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_model", mock_fetch_chat_model
    )

    async_chat_log_to_cloud = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy._async_chat_log_to_cloud",
        mock_async_chat_log_to_cloud,
    )
    mocker.patch("promptmodel.chatmodel.RegisteringMeta", MagicMock())
    chat_model = ChatModel("test", session_uuid="testuuid")

    res: Generator[LLMStreamResponse, None, None] = chat_model.run(stream=True)
    chunks: List[LLMStreamResponse] = []
    for chunk in res:
        chunks.append(chunk)

    fetch_chat_log.assert_called_once()
    fetch_chat_model.assert_called_once()
    async_chat_log_to_cloud.assert_called_once()

    assert chunks[-1].api_response is not None
    assert len([chunk for chunk in chunks if chunk.error is not None]) == 0
    assert len([chunk for chunk in chunks if chunk.parsed_outputs is not None]) == 0
    assert len([chunk for chunk in chunks if chunk.raw_output is not None]) > 0


@pytest.mark.asyncio
async def test_astream(
    mocker,
    mock_fetch_chat_log: AsyncMock,
    mock_fetch_chat_model: AsyncMock,
    mock_async_chat_log_to_cloud: AsyncMock,
):
    fetch_chat_log = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_log", mock_fetch_chat_log
    )
    fetch_chat_model = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy.fetch_chat_model", mock_fetch_chat_model
    )

    async_chat_log_to_cloud = mocker.patch(
        "promptmodel.llms.llm_proxy.LLMProxy._async_chat_log_to_cloud",
        mock_async_chat_log_to_cloud,
    )

    mocker.patch("promptmodel.chatmodel.RegisteringMeta", MagicMock())
    chat_model = ChatModel("test", session_uuid="testuuid")

    res: AsyncGenerator[LLMStreamResponse, None] = await chat_model.arun(stream=True)

    chunks: List[LLMStreamResponse] = []
    async for chunk in res:
        chunks.append(chunk)

    fetch_chat_log.assert_called_once()
    fetch_chat_model.assert_called_once()
    async_chat_log_to_cloud.assert_called_once()

    assert chunks[-1].api_response is not None
    assert len([chunk for chunk in chunks if chunk.error is not None]) == 0
    assert len([chunk for chunk in chunks if chunk.parsed_outputs is not None]) == 0
    assert len([chunk for chunk in chunks if chunk.raw_output is not None]) > 0